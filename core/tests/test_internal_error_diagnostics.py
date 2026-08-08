"""T-CHQ3/ز — الخطأ الداخلي يجب أن يحمل ما يكفي لتشخيصه.

بلاغ المالك «هي بضرب إيرور شو هاد»: الرسالة كانت «حدث خطأ داخلي في الخادم.»
عاريةً — بلا مسار ولا معرّف تتبّع ولا نوع استثناء — ونصّ الاستثناء حبيسُ طرفية
الخادم، ومن يبلّغ عن العطل ليس بالضرورة من يقرأ اللوغ.
"""
from django.test import RequestFactory, TestCase, override_settings

from core.exception_handler import custom_exception_handler


class InternalErrorDiagnosticsTest(TestCase):
    def setUp(self):
        self.context = {"request": RequestFactory().post("/api/sales/payments/")}

    def _handle(self, exc=None):
        return custom_exception_handler(exc or RuntimeError("boom"), self.context)

    def test_carries_a_trace_id_matching_the_log_line(self):
        response = self._handle()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], "internal_error")
        self.assertTrue(response.data["trace_id"])

    @override_settings(DEBUG=True)
    def test_debug_reveals_the_exception_type_and_message(self):
        response = self._handle(ValueError("لا يوجد حساب"))
        self.assertEqual(response.data["error"], "ValueError: لا يوجد حساب")

    @override_settings(DEBUG=False)
    def test_production_never_leaks_the_exception(self):
        response = self._handle(ValueError("سرّ داخلي"))
        self.assertNotIn("error", response.data)
        self.assertTrue(response.data["trace_id"])

    @override_settings(DEBUG=True)
    def test_long_exception_text_is_truncated(self):
        response = self._handle(RuntimeError("x" * 900))
        self.assertLessEqual(len(response.data["error"]), 500)
