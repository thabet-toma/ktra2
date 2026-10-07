"""«سجل الاستحقاق»: بنود كل قيد استحقاقٍ محفوظة، وفرق كل تعديلٍ بندًا بندًا.

بنود التخليص حالتُه الحالية وحدها، و«تعديل الاستحقاق» كان يكتب فوقها فتضيع بنود الأصل
(الإنتاج: SH-0014/15/16 سطرٌ «إجمالي» قبل التعديل وبعده). الآن لقطةٌ لكل قيد — الأصلي
عند الترحيل و«قبل/بعد» عند كل تعديل — تُعرض في رحلة الاستيراد وفي كشف الطرف من مصدرٍ
واحد، وتُعبّأ بنود القديم بمجموعٍ مطابق دون أن يُمسّ قيد.
"""
from io import StringIO

from django.core.management import call_command

from accounting.models import JournalHeader, JournalLine
from accounting.services import partner_account_statement
from logistics.domain.accrual_snapshots import ensure_snapshots
from logistics.models import AccrualLineSnapshot, LocalShipment, LogisticsClearance
from logistics.tests.test_accrual_adjust import D, _AccrualAdjustBase

API = "/api/logistics/accrual-snapshots/"


class AccrualSnapshotsTest(_AccrualAdjustBase):
    def _history(self, kind, doc_id):
        res = self.client.get(API, {"kind": kind, "document": doc_id}, **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def _adjust_lines(self, lines):
        res = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/adjust-accrual/",
            {"cost_lines": lines, "date": "2026-08-01"}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        return res.data

    def _books(self):
        return list(JournalLine.objects.filter(tenant=self.tenant).order_by("id").values_list(
            "id", "journal_id", "account_id", "partner_id", "debit", "credit", "description"))

    def _rows(self, snapshot):
        return {(r["type"], r["label"]): (D(r["before"]), D(r["after"]), D(r["difference"]), r["status"])
                for r in snapshot["diff"]}

    # ── عند الترحيل: لقطة الأصل لكل صنف ─────────────────────────────────────
    def test_posting_writes_the_original_snapshot_for_each_kind(self):
        clearance = self._history("clearance", self.clearance.pk)
        self.assertEqual(len(clearance), 1)
        original = clearance[0]
        self.assertEqual((original["role"], original["total"], original["detailed"]),
                         ("original", "900.00", True))
        self.assertEqual(original["journal_id"], LogisticsClearance.objects.get(pk=self.clearance.pk).journal_id)
        self.assertEqual({(l["type"], l["label"], l["amount"]) for l in original["lines"]}, {
            ("vat", "ضريبة القيمة المضافة", "300.00"),
            ("broker_commission", "عمولة المخلص", "600.00"),
        })
        self.assertIsNone(original["diff"])

        freight = self._history("freight", self.shipment.pk)
        self.assertEqual([(s["total"], s["detailed"], s["lines"][0]["type"]) for s in freight],
                         [("3600.00", False, "freight")])  # 1000$ × 3.6 — مبلغٌ واحد يُفصَّل لاحقاً
        local = self._history("local", self.local.pk)
        self.assertEqual([(s["total"], s["detailed"]) for s in local], [("450.00", False)])

    # ── عند التعديل: «بعد» بفرقه — زيادة، جديد، ثم محذوف ──────────────────────
    def test_each_adjustment_keeps_its_lines_and_the_diff_sums_to_its_journal(self):
        first = self._adjust_lines([
            {"label": "ضريبة القيمة المضافة", "amount": 300, "type": "vat"},
            {"label": "عمولة المخلص", "amount": 750, "type": "broker_commission"},
            {"label": "رسوم البيان", "amount": 90, "type": "declaration_fee"},
        ])
        second = self._adjust_lines([
            {"label": "ضريبة القيمة المضافة", "amount": 300, "type": "vat"},
            {"label": "رسوم البيان", "amount": 90, "type": "declaration_fee"},
        ])
        history = self._history("clearance", self.clearance.pk)
        self.assertEqual([(s["role"], s["total"], s["difference"]) for s in history], [
            ("original", "900.00", None),
            ("adjustment", "1140.00", "240.00"),
            ("adjustment", "390.00", "-750.00"),
        ])
        self.assertEqual([s["journal_id"] for s in history[1:]], [first["journal_id"], second["journal_id"]])
        self.assertEqual(self._rows(history[1]), {
            ("vat", "ضريبة القيمة المضافة"): (D("300"), D("300"), D("0"), "same"),
            ("broker_commission", "عمولة المخلص"): (D("600"), D("750"), D("150"), "changed"),
            ("declaration_fee", "رسوم البيان"): (D("0"), D("90"), D("90"), "new"),
        })
        self.assertEqual(self._rows(history[2])[("broker_commission", "عمولة المخلص")],
                         (D("750"), D("0"), D("-750"), "removed"))
        for snapshot, result in zip(history[1:], (first, second)):
            self.assertEqual(sum(D(r["difference"]) for r in snapshot["diff"]), D(snapshot["difference"]))
            self.assertEqual(D(snapshot["difference"]), D(result["difference"]))  # = قيد الفرق على المخلّص

    def test_local_and_freight_adjustments_are_snapshotted_too(self):
        res = self.client.post(f"/api/logistics/local-shipments/{self.local.pk}/adjust-accrual/",
                               {"amount": "500"}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        local = self._history("local", self.local.pk)
        self.assertEqual([(s["role"], s["total"], s["difference"]) for s in local],
                         [("original", "450.00", None), ("adjustment", "500.00", "50.00")])
        res = self.client.post(f"/api/logistics/shipments/{self.shipment.pk}/adjust-freight-accrual/",
                               {"freight_rate": "900", "freight_exchange_rate": "4.2"}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        freight = self._history("freight", self.shipment.pk)
        self.assertEqual([(s["total"], s["difference"]) for s in freight],
                         [("3600.00", None), ("3780.00", "180.00")])
        self.assertIn("900.00$", freight[1]["lines"][0]["label"])

    def test_chain_posted_before_the_feature_gets_its_before_snapshot_on_adjust(self):
        AccrualLineSnapshot.objects.all().delete()
        self._adjust_lines([
            {"label": "ضريبة القيمة المضافة", "amount": 300, "type": "vat"},
            {"label": "عمولة المخلص", "amount": 500, "type": "broker_commission"},
        ])
        history = self._history("clearance", self.clearance.pk)
        self.assertEqual([(s["role"], s["total"], s["detailed"]) for s in history],
                         [("original", "900.00", True), ("adjustment", "800.00", True)])
        self.assertEqual(self._rows(history[1])[("broker_commission", "عمولة المخلص")],
                         (D("600"), D("500"), D("-100"), "changed"))

    # ── التعبئة بأثرٍ رجعي: بالمطابقة وحدها، ولا قيد يُمسّ ────────────────────
    def test_fill_accepts_only_an_exact_total_and_never_touches_the_books(self):
        AccrualLineSnapshot.objects.all().delete()
        ensure_snapshots("clearance", LogisticsClearance.objects.get(pk=self.clearance.pk))
        snapshot = self._history("clearance", self.clearance.pk)[0]
        self.assertEqual((snapshot["detailed"], snapshot["lines"]),
                         (False, [{"label": "إجمالي", "type": "total", "amount": "900.00"}]))
        books, journals = self._books(), JournalHeader.objects.filter(tenant=self.tenant).count()

        short = self.client.post(f"{API}{snapshot['id']}/fill/", {"lines": [
            {"label": "عمولة المخلص", "type": "broker_commission", "amount": "600"},
            {"label": "ضريبة", "type": "vat", "amount": "299.99"},
        ]}, format="json", **self.h)
        self.assertEqual(short.status_code, 400, short.content)
        self.assertIn("899.99", short.json()["error"])
        self.assertFalse(AccrualLineSnapshot.objects.get(pk=snapshot["id"]).detailed)

        ok = self.client.post(f"{API}{snapshot['id']}/fill/", {"lines": [
            {"label": "عمولة المخلص", "type": "broker_commission", "amount": "600"},
            {"label": "ضريبة", "type": "vat", "amount": "300"},
        ]}, format="json", **self.h)
        self.assertEqual(ok.status_code, 200, ok.content)
        filled = ok.json()[0]
        self.assertEqual((filled["detailed"], [l["amount"] for l in filled["lines"]]), (True, ["600.00", "300.00"]))
        again = self.client.post(f"{API}{snapshot['id']}/fill/", {"lines": filled["lines"]}, format="json", **self.h)
        self.assertEqual(again.status_code, 400, again.content)  # ما رُحِّل ببنوده لا يُستبدل
        self.assertEqual(self._books(), books)
        self.assertEqual(JournalHeader.objects.filter(tenant=self.tenant).count(), journals)

    def test_history_is_scoped_to_the_tenant(self):
        from django.contrib.auth.models import User
        from tenants.services import create_company

        other = User.objects.create_user(username="other-snap", password="x")
        tenant = create_company("شركة أخرى", other)
        self.client.force_authenticate(user=other)
        h = {"HTTP_X_TENANT_ID": str(tenant.TenantID)}
        res = self.client.get(API, {"kind": "clearance", "document": self.clearance.pk}, **h)
        self.assertEqual(res.status_code, 400, res.content)
        snapshot = AccrualLineSnapshot.objects.filter(kind="clearance").first()
        res = self.client.post(f"{API}{snapshot.pk}/fill/", {"lines": []}, format="json", **h)
        self.assertIn(res.status_code, (403, 404), res.content)

    # ── backfill: لقطات «إجمالي» للقائم، بلا قيود ────────────────────────────
    def test_backfill_command_is_read_only_by_default_and_writes_no_journals(self):
        self._adjust_lines([
            {"label": "ضريبة القيمة المضافة", "amount": 300, "type": "vat"},
            {"label": "عمولة المخلص", "amount": 750, "type": "broker_commission"},
        ])
        AccrualLineSnapshot.objects.all().delete()
        books, journals = self._books(), JournalHeader.objects.filter(tenant=self.tenant).count()

        out = StringIO()
        call_command("backfill_accrual_snapshots", "--tenant", str(self.tenant.pk), stdout=out)
        self.assertFalse(AccrualLineSnapshot.objects.exists())
        self.assertIn("900.00", out.getvalue())
        self.assertIn("1050.00", out.getvalue())

        call_command("backfill_accrual_snapshots", "--tenant", str(self.tenant.pk), "--apply", stdout=StringIO())
        history = self._history("clearance", self.clearance.pk)
        self.assertEqual([(s["role"], s["total"], s["detailed"], s["lines"][0]["type"]) for s in history], [
            ("original", "900.00", False, "total"), ("adjustment", "1050.00", False, "total"),
        ])
        self.assertEqual(AccrualLineSnapshot.objects.count(), 4)  # تخليص ×2 + شحن + إرسالية
        self.assertEqual(self._books(), books)
        self.assertEqual(JournalHeader.objects.filter(tenant=self.tenant).count(), journals)
        out = StringIO()
        call_command("backfill_accrual_snapshots", "--tenant", str(self.tenant.pk), stdout=out)
        self.assertIn("لا ناقص", out.getvalue())

    # ── كشف الطرف: تفاصيل الحركة من اللقطة نفسها ─────────────────────────────
    def test_statement_rows_carry_the_same_breakdown(self):
        result = self._adjust_lines([
            {"label": "ضريبة القيمة المضافة", "amount": 300, "type": "vat"},
            {"label": "عمولة المخلص", "amount": 750, "type": "broker_commission"},
        ])
        rows = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.broker.id, is_supplier=True, limit=50)["results"]
        by_journal = {r["journal_id"]: r["accrual_breakdown"] for r in rows}
        history = self._history("clearance", self.clearance.pk)
        self.assertEqual(by_journal[history[0]["journal_id"]], history[0])
        self.assertEqual(by_journal[result["journal_id"]], history[1])
        self.assertEqual(by_journal[result["journal_id"]]["difference"], "150.00")
        carrier_rows = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.carrier.id, is_supplier=True, limit=50)["results"]
        self.assertEqual([r["accrual_breakdown"]["total"] for r in carrier_rows], ["450.00"])
        self.assertTrue(LocalShipment.objects.get(pk=self.local.pk).is_posted)
