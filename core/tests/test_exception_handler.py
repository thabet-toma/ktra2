"""P-B-2: Django ValidationError → 400 via custom exception handler."""
from django.core.exceptions import ValidationError as DjangoVE
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from core.exception_handler import custom_exception_handler


class _RaisingView(APIView):
    # موضوع الاختبار هو exception handler لا المصادقة — الافتراضي العام أصبح
    # IsAuthenticated (task11 R2-B) فنعفي هذه الـ view التجريبية صراحةً.
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        raise DjangoVE("هذا حقل مطلوب")


class ExceptionHandlerTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_django_ve_becomes_400(self):
        view = _RaisingView.as_view()
        request = self.factory.get("/test/")
        resp = view(request)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_django_ve_detail_in_response(self):
        view = _RaisingView.as_view()
        request = self.factory.get("/test/")
        resp = view(request)
        self.assertIn("هذا حقل مطلوب", str(resp.data))

    def test_django_ve_message_dict(self):
        exc = DjangoVE({"name": ["الاسم مطلوب"], "code": ["الكود موجود"]})
        response = custom_exception_handler(exc, {})
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)
        self.assertIn("code", response.data)
