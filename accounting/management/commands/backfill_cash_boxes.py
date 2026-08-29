"""T-CASHBOX — يربط صناديق ما قبل توحيد الإنشاء بشجرة الحسابات، ويُسوّي تاريخها.

مسألتان تركهما المسار القديم (نداءان من المتصفح: وثيقة الصندوق ثم حسابه):

1. **صناديق بلا حساب** — سقط النداء الثاني فبقي الصندوق بلا وجهٍ في الدفاتر.
   `--link` ينشئ لكلٍّ منها حساباً تحت «1110» ويربطه.

2. **تاريخٌ خارج الدفاتر** — حركات الصندوق القديمة (ومنها دفعات وكيل الشحن التي
   كانت تُكتب في المرآة بلا قيد إطلاقاً) لا يعرفها الأستاذ. `--history` يرحّل
   **قيداً افتتاحياً واحداً لكل صندوق** بفرق رصيد المرآة عن الأستاذ في تاريخ
   القطع — قرار المالك: دفاتر نظيفة بقيدٍ واحد، لا ترحيل حركة-بحركة يكتب في
   فتراتٍ سابقة قد تكون مقفلة.

بلا خيارات: تقريرٌ فقط، لا كتابة. والأمر idempotent — إعادة تشغيله لا تضاعف.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.cashbox import get_cash_box_capital_account
from accounting.models import CashBoxLedgerAccount
from accounting.services import cash_box_balance, create_cash_box, post_journal
from tenants.models import Tenant

OPENING_REFERENCE = "CASHBOX_LEGACY_OPENING"


class Command(BaseCommand):
    help = "يربط الصناديق القديمة بشجرة الحسابات ويُسوّي أرصدتها التاريخية."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="رقم الشركة (الكل إن غاب)")
        parser.add_argument("--link", action="store_true",
                            help="أنشئ حساباً في الشجرة لكل صندوق مرآة بلا ربط")
        parser.add_argument("--defaults", action="store_true",
                            help="عيّن صندوقاً افتراضياً لكل شركة لا تملك واحداً")
        parser.add_argument("--history", action="store_true",
                            help="رحّل قيد التسوية الافتتاحي لفرق المرآة عن الأستاذ")
        parser.add_argument("--as-of", type=str, default=None,
                            help="تاريخ القطع لقيد التسوية (افتراضي: اليوم)")
        parser.add_argument(
            "--allow-decrease", action="store_true",
            help="اسمح بقيد تسوية **يُنقص** رصيد الأستاذ (خطر — اقرأ التحذير)")

    def handle(self, *args, **opts):
        from django.utils import timezone

        tenants = (
            Tenant.objects.filter(pk=opts["tenant"]) if opts.get("tenant")
            else Tenant.objects.all()
        )
        as_of = opts.get("as_of") or timezone.localdate()
        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nالشركة {tenant.pk} — {tenant.CompanyName}"))
            self._link_orphans(tenant, apply=opts["link"])
            self._ensure_default(tenant, apply=opts["defaults"])
            self._reconcile(tenant, as_of=as_of, apply=opts["history"],
                            allow_decrease=opts["allow_decrease"])
        if not any(opts[k] for k in ("link", "defaults", "history")):
            self.stdout.write(self.style.WARNING(
                "\nتقريرٌ فقط — أضف --link و/أو --defaults و/أو --history للتنفيذ."))

    # ── 1) صناديق المرآة بلا حساب في الشجرة ──────────────────────────────
    def _link_orphans(self, tenant, *, apply):
        from bridge.models import FirestoreMirrorDoc

        docs = FirestoreMirrorDoc.objects.filter(
            tenant=tenant, path__startswith="cashBoxes/")
        linked = set(
            CashBoxLedgerAccount.objects.filter(tenant=tenant)
            .values_list("external_id", flat=True)
        )
        orphans = [d for d in docs if str(d.path.split("/", 1)[-1]) not in linked]
        if not orphans:
            self.stdout.write("  كل الصناديق مربوطة بالشجرة.")
            return
        for doc in orphans:
            ext = doc.path.split("/", 1)[-1]
            data = doc.data or {}
            name = str(data.get("name") or f"صندوق {ext[:8]}")[:100]
            currency = str(data.get("currency") or "ILS")[:3]
            if not apply:
                self.stdout.write(f"  [تقرير] صندوق بلا حساب: {name} ({ext})")
                continue
            box = create_cash_box(
                tenant=tenant, name=name, currency_code=currency, external_id=ext)
            self.stdout.write(self.style.SUCCESS(
                f"  [تم] رُبط {name} → {box.account.code}"))

    # ── 2) شركة بصناديق بلا افتراضي مُعلَن ───────────────────────────────
    def _ensure_default(self, tenant, *, apply):
        """يعيّن افتراضياً لشركةٍ لا تملك واحداً — وإلا بقي الحلّ عشوائياً.

        الصناديق التي أُنشئت قبل `is_default` كلّها `False`، فيسقط
        `resolve_cash_account` على «أوّل صندوق نشط بالمعرّف»: ترتيبُ إدخالٍ
        قديم يقرّر من أين يُدفع — وهو صنف العشوائية نفسه الذي أُصلح.
        الترجيح: صندوق إعدادات المبيعات ← إعدادات الشراء ← أقدم صندوق نشط.
        """
        from sales.models import SalesSettings
        from logistics.models import PurchaseSettings

        boxes = CashBoxLedgerAccount.objects.filter(tenant=tenant, is_active=True)
        if not boxes.exists():
            return
        if boxes.filter(is_default=True).exists():
            self.stdout.write("  الافتراضي مُعلَن سلفاً.")
            return

        preferred = None
        for model in (SalesSettings, PurchaseSettings):
            row = model.objects.filter(tenant=tenant).first()
            acc_id = getattr(row, "default_cash_account_id", None) if row else None
            if acc_id:
                preferred = boxes.filter(account_id=acc_id).first()
                if preferred:
                    break
        chosen = preferred or boxes.order_by("id").first()
        if not apply:
            self.stdout.write(
                f"  [تقرير] بلا صندوق افتراضي — المرشّح: {chosen.name}"
                f" ({'من الإعدادات' if preferred else 'الأقدم'})")
            return
        with transaction.atomic():
            boxes.filter(is_default=True).update(is_default=False)
            chosen.is_default = True
            chosen.save(update_fields=["is_default"])
        self.stdout.write(self.style.SUCCESS(f"  [تم] الافتراضي = {chosen.name}"))

    # ── 3) فرق المرآة عن الأستاذ ⇒ قيد تسوية افتتاحي واحد ────────────────
    def _reconcile(self, tenant, *, as_of, apply, allow_decrease=False):
        from bridge.models import FirestoreMirrorDoc
        from accounting.models import JournalHeader

        capital = get_cash_box_capital_account(tenant)
        boxes = CashBoxLedgerAccount.objects.filter(
            tenant=tenant).select_related("account")
        for box in boxes:
            if JournalHeader.objects.filter(
                tenant=tenant, reference_type=OPENING_REFERENCE, reference_id=box.pk,
            ).exists():
                continue  # سُوِّي سابقاً — الأمر idempotent
            doc = FirestoreMirrorDoc.objects.filter(
                path=f"cashBoxes/{box.external_id}").first()
            mirror_balance = Decimal(str((doc.data or {}).get("currentBalance") or 0)) if doc else Decimal("0")
            ledger_balance = cash_box_balance(box, as_of=as_of)
            delta = (mirror_balance - ledger_balance).quantize(Decimal("0.01"))
            if delta == 0:
                continue

            # **حارس المال**: هذا الأمر يُدخل نقداً قديماً لم يرَه الأستاذ — أي
            # فائضاً في المرآة. أما مرآةٌ **أقلّ** من الأستاذ فمعناها في الغالب
            # أنها هُجرت لا أن مالاً نقص: على قاعدة الإنتاج وُجدت شركةٌ مرآتها
            # صفر وأستاذها ١٣٥٬٤٨٦ من فواتير وسندات مرحّلة فعلاً — وقيدُ تسويةٍ
            # سالب كان سيمحوها. فالنقصان لا يُرحَّل إلا بطلبٍ صريح.
            if delta < 0 and not allow_decrease:
                self.stdout.write(self.style.WARNING(
                    f"  [تخطٍّ] {box.name}: المرآة ({mirror_balance}) أقلّ من الأستاذ "
                    f"({ledger_balance}) — تُخطّى. المرآة مهجورة على الأرجح؛ "
                    f"التسوية بالنقصان تحتاج --allow-decrease بعد مراجعة يدوية."))
                continue
            if not apply:
                self.stdout.write(
                    f"  [تقرير] {box.name}: المرآة {mirror_balance} · الأستاذ "
                    f"{ledger_balance} · الفرق {delta}")
                continue
            if capital is None:
                self.stdout.write(self.style.ERROR(
                    f"  [فشل] {box.name}: لا حساب رأس مال (Equity) لتسوية الفرق."))
                continue
            label = f"تسوية رصيد افتتاحي — {box.name}"
            positive = delta > 0
            magnitude = abs(delta)
            with transaction.atomic():
                post_journal(
                    tenant_id=tenant.pk, transaction_date=as_of,
                    reference_type=OPENING_REFERENCE, reference_id=box.pk,
                    description=label,
                    lines_data=[
                        {"account": box.account_id,
                         "debit": magnitude if positive else Decimal("0"),
                         "credit": Decimal("0") if positive else magnitude,
                         "description": label},
                        {"account": capital.id,
                         "debit": Decimal("0") if positive else magnitude,
                         "credit": magnitude if positive else Decimal("0"),
                         "description": label},
                    ],
                )
            self.stdout.write(self.style.SUCCESS(
                f"  [تم] سُوِّي {box.name} بفرق {delta}"))
