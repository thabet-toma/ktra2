"""G11: رؤوس الأمان — CSP وnosniff وreferrer وframe على ردود Django."""
from django.test import TestCase


class SecurityHeadersTest(TestCase):
    def test_csp_header_present_and_blocks_framing(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        csp = resp.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_standard_security_headers_present(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("Referrer-Policy"), "same-origin")
        # XFrameOptionsMiddleware + X_FRAME_OPTIONS=DENY
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
