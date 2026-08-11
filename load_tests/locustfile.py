# -*- coding: utf-8 -*-
"""سيناريو حمل واقعي لـK.T.R.A — المرحلة 6 من docs/REFACTOR_PROMPTS.md.

الخليط المرجّح (كما نصّ برومت المرحلة 6):
    40% فتح قوائم (فواتير بيع، منتجات، عملاء، قيود، حركات مخزون، فواتير شراء)
    25% فتح تفاصيل مستند
    15% إنشاء فاتورة بيع كاملة (ترويسة + بنود [+ ترحيل])
    10% تقرير
    10% بحث/autocomplete

عقود حقيقية (مستخرَجة بالقراءة من `*/urls.py` و`*/views.py`، لا مخترعة):
  • المصادقة: `POST /api/hr/auth/login/` بـ`{email, password}` تُرجع `{token}`،
    ثم `Authorization: Token <key>` على كل طلب (`frontend_v2/services/restApi.ts:140`).
  • العزل: ترويسة `X-Tenant-Id` إلزامية عملياً — `core/tenant_utils.py:33-45`
    لا يستنتج الشركة إلا إذا كانت الشركة الوحيدة في القاعدة، وهو ما لا يصحّ هنا
    (نوزّع على 3-5 شركات عمداً).
  • الترقيم: بعد P0-5 صارت قوائم الفئة أ على `EnforcedPageNumberPagination`
    (فواتير البيع/القيود/حركات المخزون…) فترد `{results, count, ...}`؛ وقوائم
    الفئة ب على `OptionalPageNumberPagination` فترد مصفوفة خام بلا `?page=`.
    لذلك كل طلب قائمة هنا يمرّر `?page=`، وطلبات الـautocomplete وحدها تبقى بلا
    ترقيم لأنها المسار الفعلي للمحدِّدات (`view=lookup` / `lookup/`).
  • تسجيل الدخول عليه حدّ محاولات (P0-13، `hr/auth_api.py:171`: 10 إخفاقات لكل
    بريد/IP في 15 دقيقة). لذلك **التوكن يُجلَب مرة واحدة لكل حساب ويُشارَك بين
    كل المستخدمين الافتراضيين على ذلك الحساب** — لا تسجيل دخول لكل مستخدم.

التشغيل (التفاصيل في docs/LOAD_TEST_RESULTS.md):
    export KTRA_LOADTEST_PASSWORD='...'          # كلمة مرور حسابات الحمل
    locust -f load_tests/locustfile.py --host http://127.0.0.1:8000 \
           --users 50 --spawn-rate 5 --run-time 5m --headless

مصدر الهويات: ملف بيان يكتبه أمر الـseed
(`python manage.py seed_load_test_data ... --manifest load_tests/seed_manifest.json`).
البيان لا يحمل أي كلمة مرور — كلمة المرور من متغيّر البيئة وحده.
"""
from __future__ import annotations

import json
import os
import random
from datetime import date, timedelta

from gevent.lock import Semaphore
from locust import HttpUser, between, events, task

# ── تهيئة من البيئة ────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))

MANIFEST_PATH = os.environ.get(
    "KTRA_LOADTEST_MANIFEST", os.path.join(_HERE, "seed_manifest.json"),
)
PASSWORD = os.environ.get("KTRA_LOADTEST_PASSWORD", "")
#: ترحيل الفاتورة بعد إنشائها (المسار الثقيل: قيد + حركات مخزون + COGS).
#: 1 = افتراضياً مُفعَّل — «فاتورة بيع كاملة» تعني وصولها للدفاتر.
POST_CREATED_INVOICES = os.environ.get("KTRA_LOADTEST_POST_INVOICES", "1") == "1"
#: فحص العزل تحت الحمل: نسبة طلبات التفاصيل التي تستهدف مستند شركة **أخرى**
#: ويجب أن تُردّ (403/404). 0 يعطّل الفحص.
ISOLATION_PROBE_RATIO = float(os.environ.get("KTRA_LOADTEST_ISOLATION_RATIO", "0.1"))

SEARCH_TERMS = ["صنف", "LT", "عميل", "01", "زبون", "A", "شركة", "20"]


class ManifestError(RuntimeError):
    pass


def _load_manifest() -> dict:
    if not os.path.exists(MANIFEST_PATH):
        raise ManifestError(
            f"ملف البيان غير موجود: {MANIFEST_PATH}\n"
            "شغّل أمر الـseed أولاً على قاعدة اختبار معزولة:\n"
            "  python manage.py seed_load_test_data --i-know-what-im-doing "
            "--password '<pw>' --manifest load_tests/seed_manifest.json"
        )
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    tenants = data.get("tenants") or []
    if len(tenants) < 3:
        raise ManifestError(
            "البيان يحمل أقل من 3 شركات — اختبار العزل يحتاج 3-5 شركات على الأقل."
        )
    return data


MANIFEST: dict = {}
#: عدّاد توزيع المستخدمين الافتراضيين على الشركات (round-robin).
_USER_SEQ = 0
_SEQ_LOCK = Semaphore()
#: توكن واحد لكل بريد، يُجلَب مرة ويُعاد استعماله (حدّ محاولات الدخول P0-13).
_TOKENS: dict[str, str] = {}
_TOKEN_LOCKS: dict[str, Semaphore] = {}
_TOKEN_LOCKS_GUARD = Semaphore()


@events.test_start.add_listener
def _on_test_start(environment, **_kwargs):  # noqa: ANN001
    global MANIFEST
    if not PASSWORD:
        raise ManifestError(
            "KTRA_LOADTEST_PASSWORD غير مضبوط — لا كلمات مرور داخل الريبو."
        )
    MANIFEST = _load_manifest()
    names = [t["company_name"] for t in MANIFEST["tenants"]]
    print(f"[ktra-load] شركات الاختبار ({len(names)}): {', '.join(names)}")


def _next_tenant() -> dict:
    """يوزّع المستخدمين الافتراضيين بالتناوب على شركات البيان."""
    global _USER_SEQ
    with _SEQ_LOCK:
        idx = _USER_SEQ
        _USER_SEQ += 1
    tenants = MANIFEST["tenants"]
    return tenants[idx % len(tenants)]


def _token_lock(email: str) -> Semaphore:
    with _TOKEN_LOCKS_GUARD:
        lock = _TOKEN_LOCKS.get(email)
        if lock is None:
            lock = _TOKEN_LOCKS[email] = Semaphore()
        return lock


class KtraUser(HttpUser):
    """مستخدم افتراضي مربوط بشركة واحدة طوال حياته."""

    wait_time = between(1, 5)

    # ── دورة الحياة ────────────────────────────────────────────────────────
    def on_start(self):
        self.tenant = _next_tenant()
        self.tenant_id = self.tenant["tenant_id"]
        self.email = self.tenant["user_email"]
        self.currency_id = self.tenant.get("currency_id")
        self.customer_ids: list[int] = list(self.tenant.get("customer_ids") or [])
        self.product_ids: list[int] = list(self.tenant.get("product_ids") or [])
        self.invoice_ids: list[int] = list(self.tenant.get("invoice_ids") or [])
        # مستندات شركة أخرى — يجب أن تُردّ. مصدر فحص العزل تحت الحمل.
        self.foreign_invoice_ids: list[int] = [
            iid
            for other in MANIFEST["tenants"]
            if other["tenant_id"] != self.tenant_id
            for iid in (other.get("invoice_ids") or [])[:20]
        ]
        self.token = self._login()
        self.client.headers.update(
            {
                "Authorization": f"Token {self.token}",
                "X-Tenant-Id": str(self.tenant_id),
                "Content-Type": "application/json",
            }
        )

    def _login(self) -> str:
        """توكن مشترك لكل حساب — تسجيل دخول واحد مهما بلغ عدد المستخدمين."""
        cached = _TOKENS.get(self.email)
        if cached:
            return cached
        with _token_lock(self.email):
            cached = _TOKENS.get(self.email)
            if cached:
                return cached
            with self.client.post(
                "/api/hr/auth/login/",
                json={"email": self.email, "password": PASSWORD},
                name="POST /api/hr/auth/login/",
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    response.failure(
                        f"فشل الدخول ({response.status_code}) — "
                        f"راجع KTRA_LOADTEST_PASSWORD وبيانات الـseed."
                    )
                    raise ManifestError(
                        f"login failed for {self.email}: {response.status_code}"
                    )
                token = response.json().get("token")
                if not token:
                    response.failure("استجابة دخول بلا توكن")
                    raise ManifestError("login response without token")
                response.success()
            _TOKENS[self.email] = token
            return token

    # ── أدوات ──────────────────────────────────────────────────────────────
    @staticmethod
    def _period() -> tuple[str, str]:
        today = date.today()
        return (today - timedelta(days=180)).isoformat(), today.isoformat()

    def _remember_ids(self, payload) -> None:
        """يلتقط معرّفات من ردّ القائمة لتغذية طلبات التفاصيل."""
        rows = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return
        ids = [r.get("id") for r in rows if isinstance(r, dict) and r.get("id")]
        if ids:
            self.invoice_ids = (self.invoice_ids + ids)[-400:]

    # ── 40% — القوائم ──────────────────────────────────────────────────────
    @task(20)
    def browse_sales_invoices(self):
        """قائمة فواتير البيع — ترقيم إلزامي (EnforcedPageNumberPagination)."""
        page = random.randint(1, 5)
        with self.client.get(
            f"/api/sales/invoices/?page={page}&page_size=50",
            name="GET /api/sales/invoices/?page",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                self._remember_ids(response.json())
                response.success()
            elif response.status_code == 404 and page > 1:
                response.success()  # صفحة خارج المدى ليست خطأ أداء

    @task(6)
    def browse_products(self):
        self.client.get(
            f"/api/inventory/products/?page={random.randint(1, 4)}&page_size=50",
            name="GET /api/inventory/products/?page",
        )

    @task(4)
    def browse_partners(self):
        self.client.get(
            "/api/partners/?partner_type=Customer&page=1&page_size=50",
            name="GET /api/partners/?page",
        )

    @task(4)
    def browse_journals(self):
        self.client.get(
            f"/api/accounting/journals/?page={random.randint(1, 5)}&page_size=50",
            name="GET /api/accounting/journals/?page",
        )

    @task(4)
    def browse_stock_movements(self):
        self.client.get(
            f"/api/inventory/stock-movements/?page={random.randint(1, 5)}&page_size=50",
            name="GET /api/inventory/stock-movements/?page",
        )

    @task(2)
    def browse_purchase_invoices(self):
        self.client.get(
            "/api/logistics/purchase-invoices/?page=1&page_size=50",
            name="GET /api/logistics/purchase-invoices/?page",
        )

    # ── 25% — تفاصيل مستند ────────────────────────────────────────────────
    @task(25)
    def open_document(self):
        """فتح فاتورة بيع — وأحياناً فاتورة شركة أخرى للتحقق من العزل."""
        if self.foreign_invoice_ids and random.random() < ISOLATION_PROBE_RATIO:
            self._isolation_probe()
            return
        if not self.invoice_ids:
            self.browse_sales_invoices()
            return
        invoice_id = random.choice(self.invoice_ids)
        with self.client.get(
            f"/api/sales/invoices/{invoice_id}/",
            name="GET /api/sales/invoices/{id}/",
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                # حُذفت/لم تعد ضمن الشركة — ليست فشل أداء
                self.invoice_ids = [i for i in self.invoice_ids if i != invoice_id]
                response.success()

    def _isolation_probe(self):
        """طلب مستند شركة أخرى بنفس التوكن — نجاحه = تسريب بيانات."""
        foreign_id = random.choice(self.foreign_invoice_ids)
        with self.client.get(
            f"/api/sales/invoices/{foreign_id}/",
            name="GET /api/sales/invoices/{foreign_id}/ [isolation]",
            catch_response=True,
        ) as response:
            if response.status_code in (403, 404):
                response.success()
            elif response.status_code == 200:
                response.failure(
                    "خرق عزل: مستند شركة أخرى قابل للقراءة تحت الحمل"
                )

    # ── 15% — إنشاء فاتورة بيع كاملة ──────────────────────────────────────
    @task(15)
    def create_sales_invoice(self):
        if not (self.customer_ids and self.product_ids and self.currency_id):
            return
        line_count = random.randint(2, 5)
        payload = {
            "customer": random.choice(self.customer_ids),
            "invoice_date": date.today().isoformat(),
            "currency": self.currency_id,
            "invoice_type": random.choice(["cash", "credit"]),
            "auto_post": False,
            "notes": "locust load test",
            "lines": [
                {
                    "product": random.choice(self.product_ids),
                    "quantity": str(random.randint(1, 6)),
                    "unit_price": f"{random.uniform(10, 400):.2f}",
                    "line_discount": "0",
                }
                for _ in range(line_count)
            ],
        }
        with self.client.post(
            "/api/sales/invoices/",
            json=payload,
            name="POST /api/sales/invoices/",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                return
            body = response.json()
            invoice_id = body.get("id")
            if invoice_id:
                self.invoice_ids.append(invoice_id)
            if body.get("auto_post_error"):
                response.failure(f"auto_post_error: {body['auto_post_error']}")
                return
            response.success()
        if POST_CREATED_INVOICES and invoice_id:
            self.client.post(
                f"/api/sales/invoices/{invoice_id}/post/",
                json={},
                name="POST /api/sales/invoices/{id}/post/",
            )

    # ── 10% — تقارير ──────────────────────────────────────────────────────
    @task(10)
    def run_report(self):
        start, end = self._period()
        key = random.choice(
            [
                "sales-summary",
                "sales-by-customer",
                "sales-invoices",
                "receivables-aging",
                "payables-aging",   # P0-9 سابقاً — أثقل تقرير في التدقيق
                "stock-valuation",
                "customer-balances",
            ]
        )
        self.client.get(
            f"/api/reports/{key}/?from={start}&to={end}",
            name=f"GET /api/reports/{key}/",
        )

    # ── 10% — بحث / autocomplete ──────────────────────────────────────────
    @task(6)
    def autocomplete_products(self):
        """محدِّد الأصناف داخل المحرّرات — `view=lookup` بمصفوفة خام (بلا ترقيم)."""
        term = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/api/inventory/products/?view=lookup&search={term}",
            name="GET /api/inventory/products/?view=lookup&search",
        )

    @task(4)
    def autocomplete_partners(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/api/partners/lookup/?limit=50&search={term}",
            name="GET /api/partners/lookup/?search",
        )
