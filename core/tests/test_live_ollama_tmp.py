"""اختبار حي مؤقت — يتصل بـ Ollama السحابي فعلياً. يُحذف بعد التحقق.

يعمل فقط عند ضبط OLLAMA_API_KEY في البيئة (وإلا يُتخطّى).
"""
import os
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory

from core import ollama_assistant
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

LIVE_KEY = os.environ.get("OLLAMA_API_KEY", "").strip()


@pytest.mark.skipif(not LIVE_KEY, reason="no OLLAMA_API_KEY in env")
def test_live_chat_calls_tool_and_answers(settings):
    settings.OLLAMA_BASE_URL = "https://ollama.com/v1"
    settings.OLLAMA_API_KEY = LIVE_KEY
    settings.OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:397b")
    settings.OLLAMA_ASSISTANT_TIMEOUT = 180

    owner = User.objects.create_user(username="live", password="x", is_superuser=True)
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    a = create_company("شركة الاختبار الحي", owner)
    ashraf = Partner.objects.create(tenant=a, name="أشرف عجل", partner_type="Customer")
    SalesInvoice.objects.create(
        tenant=a, invoice_number="LS-1", customer=ashraf, currency=cur,
        invoice_date="2026-06-15", invoice_kind="sale",
        status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("600"),
    )

    req = RequestFactory().post("/api/assistant/chat/", HTTP_X_TENANT_ID=str(a.TenantID))
    req.user = owner

    reply = ollama_assistant.chat("كم بعنا لأشرف عجل؟", req)
    print("\n=== LIVE REPLY ===\n", reply, "\n==================")
    assert reply
    assert "600" in reply
