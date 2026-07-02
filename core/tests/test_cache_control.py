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
