"""NoStoreAPIMiddleware: ردود الـ API تخرج بترويسة no-store (منع كاش المتصفح)."""
from django.test import TestCase


class NoStoreAPIMiddlewareTest(TestCase):
    def test_api_response_has_no_store(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        cc = resp.headers.get("Cache-Control", "")
        self.assertIn("no-store", cc)
        self.assertIn("no-cache", cc)

    def test_head_api_response_has_no_store(self):
        # نبض الاتصال (useOnlineStatus) يستخدم HEAD — يجب أن يحمل الترويسة أيضاً.
        resp = self.client.head("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("no-store", resp.headers.get("Cache-Control", ""))


class CorsPreflightTest(TestCase):
    def test_active_branch_header_is_allowed(self):
        resp = self.client.options(
            "/api/health/",
            HTTP_ORIGIN="https://smart.ktragroup.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-branch-id,x-tenant-id",
        )

        self.assertEqual(resp.status_code, 200)
        allowed = {
            header.strip().lower()
            for header in resp.headers.get("Access-Control-Allow-Headers", "").split(",")
        }
        self.assertIn("x-tenant-id", allowed)
        self.assertIn("x-branch-id", allowed)
