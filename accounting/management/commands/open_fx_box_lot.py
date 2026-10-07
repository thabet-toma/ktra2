"""يفتح صندوق عملة أجنبية بلا طبقات FIFO بطبقة افتتاحية من الجرد الفعلي — بطلب المالك.

إنتاج كترا: صندوق الدولار (الحساب 108) بلا طبقات ورصيده الدفتري سالب (دفعاتٌ خرجت
منه ولم يُسجَّل تمويلها)، فـFIFO معطّل عليه ومقارنة الجرد به بلا معنى.

    python manage.py open_fx_box_lot --tenant 1 --box-account 108 --fc 12000 \\
        --rate 3.65 --date 2026-10-07 --offset-account 3101
    ... --apply

القيم كلها يقرّرها المالك — لا افتراضيات. القراءة (الافتراض) تطبع الوضع وما سيُكتب؛
--apply ينفّذ `fx_fifo.open_box_with_counted_lot` ويطبع قبل/بعد: box_fc_balance
وbox_ils_value ورصيد الصندوق ورصيد حساب المقابل.
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounting.fx_fifo import (
    account_base_balance,
    box_fc_balance,
    box_ils_value,
    open_box_with_counted_lot,
)
from accounting.models import Account, CashBoxLedgerAccount


class Command(BaseCommand):
    help = "طبقة افتتاحية لصندوق عملة أجنبية من الجرد الفعلي (قراءة افتراضاً، --apply للكتابة)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True)
        parser.add_argument("--box-account", required=True, help="كود حساب الصندوق (مثل 108)")
        parser.add_argument("--fc", required=True, help="الدولارات الموجودة فعلاً بالعدّ")
        parser.add_argument("--rate", required=True, help="سعر الطبقة: شيكل لكل دولار")
        parser.add_argument("--date", required=True, help="تاريخ الطبقة YYYY-MM-DD")
        parser.add_argument("--offset-account", required=True, help="كود حساب المقابل")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        tenant_id = o["tenant"]
        try:
            date = datetime.date.fromisoformat(o["date"])
            fc, rate = Decimal(o["fc"]), Decimal(o["rate"])
        except (ValueError, InvalidOperation):
            raise CommandError("--date بصيغة YYYY-MM-DD و--fc و--rate أرقام.")
        account = Account.objects.filter(tenant_id=tenant_id, code=o["box_account"]).first()
        box = account and CashBoxLedgerAccount.objects.filter(
            tenant_id=tenant_id, account=account).select_related("account").first()
        if box is None:
            raise CommandError(f"الحساب {o['box_account']} ليس صندوقاً لهذه الشركة.")
        offset = Account.objects.filter(tenant_id=tenant_id, code=o["offset_account"]).first()
        if offset is None:
            raise CommandError(f"لا حساب بالكود {o['offset_account']} لهذه الشركة.")

        w = self.stdout.write
        w(f"الصندوق: {box.name} ({account.code}) بعملة {box.currency_code}، "
          f"طبقاته الآن: {box.fx_lots.count()}")
        w(f"المقابل: {offset.code} {offset.name}")
        self._state("قبل", box, offset)
        w(f"المطلوب: طبقة {fc} بسعر {rate} = {(fc * rate).quantize(Decimal('0.01'))} ₪ "
          f"بتاريخ {date}، ورصيد الصندوق يصير مثلها (الفرق على المقابل).")
        if not o["apply"]:
            return
        try:
            lot, adjust = open_box_with_counted_lot(box, fc, rate, date=date, offset_account=offset)
        except ValidationError as exc:
            raise CommandError(f"لم يتغيّر شيء: {' '.join(exc.messages)}")
        w(self.style.SUCCESS(
            f"طبقة #{lot.pk} بقيد #{lot.journal_id}"
            + (f"، وتسوية بقيد #{adjust.pk}" if adjust else "، بلا تسوية (الرصيد كان صفراً)")))
        self._state("بعد", box, offset)

    def _state(self, label, box, offset):
        self.stdout.write(
            f"{label}: box_fc_balance={box_fc_balance(box)} box_ils_value={box_ils_value(box)} "
            f"رصيد الصندوق={account_base_balance(box.account_id)} "
            f"رصيد المقابل={account_base_balance(offset.pk)}")
