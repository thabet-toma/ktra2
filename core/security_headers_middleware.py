"""
G11: Content-Security-Policy لردود Django.

الواجهة الأمامية (SPA) تُستضاف منفصلة (smart.ktragroup.com)، وDjango يخدم الـAPI
وواجهة الإدارة وDRF التصفّحية وصفحات الأخطاء فقط — فوضع CSP هنا يحمي تلك الأسطح دون
أن يمسّ تصيير الـSPA. رؤوس الأمان الأخرى (nosniff/referrer/xframe/HSTS) تُضبط عبر
إعدادات Django القياسية في settings.py.

السياسة قابلة للضبط عبر البيئة دون تعديل كود:
  - CSP_DISABLED=1        → تعطيل كامل (مخرج طوارئ).
  - CSP_REPORT_ONLY=1     → وضع الإبلاغ فقط (لا يمنع، يُبلّغ) — للطرح التدريجي.
  - CSP_POLICY="..."      → استبدال السياسة الافتراضية بالكامل.

الافتراضي يسمح بما تحتاجه واجهة إدارة Django وDRF (أنماط/سكربتات inline) ويمنع
التأطير (frame-ancestors 'none') ومصادر السكربت الخارجية.
"""
import os

_DEFAULT_POLICY = "; ".join([
    "default-src 'self'",
    # واجهة إدارة Django وDRF التصفّحية تستخدمان سكربتات/أنماط inline.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


def _truthy(name):
    return os.environ.get(name, "0").lower() in ("1", "true", "yes")


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.disabled = _truthy("CSP_DISABLED")
        self.policy = os.environ.get("CSP_POLICY") or _DEFAULT_POLICY
        self.header = (
            "Content-Security-Policy-Report-Only"
            if _truthy("CSP_REPORT_ONLY")
            else "Content-Security-Policy"
        )

    def __call__(self, request):
        response = self.get_response(request)
        if not self.disabled and self.header not in response:
            response[self.header] = self.policy
        return response
