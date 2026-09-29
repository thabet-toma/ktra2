"""ترويسة مستندات الشركة — مصدر واحد تستورده `docshare` و`after_sales`.

بلا استيراد نموذج: الدالة تقرأ `tenant.settings` كسولاً بـ`getattr`، فتصلح لأي
وحدة دون أن تجرّ معها اعتماداً على نماذج `tenants`.
"""

#: هوية الشركة كما تُطبع في ترويسة المستند — لا إعداداتها ولا فترتها المالية
#: ولا نسبها الافتراضية. هذه أيضاً قائمة بيضاء يقيسها اختبار التسريب.
COMPANY_FIELDS = (
    "company_name_primary", "company_name_sub", "address", "po_box",
    "phone", "fax", "email", "logo_url",
    "licensed_dealer_no", "income_tax_file_no",
)


def company_card(tenant) -> dict:
    """ترويسة المستند. شركة بلا صفّ إعدادات تُعرض باسمها المسجَّل لا فارغة."""
    tenant_settings = getattr(tenant, "settings", None)
    if tenant_settings is None:
        return {field: "" for field in COMPANY_FIELDS} | {
            "company_name_primary": tenant.CompanyName or "",
        }
    card = {
        field: (getattr(tenant_settings, field, None) or "")
        for field in COMPANY_FIELDS
    }
    if not card["company_name_primary"]:
        card["company_name_primary"] = tenant.CompanyName or ""
    return card
