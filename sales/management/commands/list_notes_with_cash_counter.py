"""تقرير فقط: الإشعارات المدينة/الدائنة المرحّلة التي حسابها المقابل نقدٌ أو بنكٌ أو شيكات.

الإشعار تسويةٌ لا دفع؛ مقابلٌ نقديٌّ يجعله سندَ صرفٍ/قبضٍ بلا حركة نقد (DN-0001 على
الإنتاج: Dr ذمّة المخلّص / Cr «صندوق شيكل» أنقص الصندوق). الحارس الآن يرفضه
(`sales/services/orders.py` — `credit_debit_counter_account_error`)، وهذا الأمر يسرد
ما رُحِّل قبله. **لا يعدّل شيئاً** — التصحيح يدوي: إلغاء الترحيل ثم تعديل المقابل وإعادة
الترحيل من شاشة «إشعارات مدينة/دائنة».

    python manage.py list_notes_with_cash_counter --tenant 1
    python manage.py list_notes_with_cash_counter          # كل الشركات
"""
from django.core.management.base import BaseCommand

from accounting.api import money_account_kind
from sales.models import CreditDebitNote

KIND_LABEL = {"cash": "صندوق", "bank": "بنك", "cheques": "شيكات"}


class Command(BaseCommand):
    help = "يسرد الإشعارات المرحّلة التي حسابها المقابل نقد/بنك/شيكات — بلا تعديل."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="معرّف الشركة (افتراضياً كل الشركات).")

    def handle(self, *args, **options):
        notes = (
            CreditDebitNote.objects.filter(status=CreditDebitNote.STATUS_POSTED)
            .select_related("partner", "counter_account", "currency")
            .order_by("tenant_id", "note_date", "id")
        )
        if options.get("tenant"):
            notes = notes.filter(tenant_id=options["tenant"])
        found = 0
        for note in notes:
            kind = money_account_kind(note.counter_account)
            if not kind:
                continue
            found += 1
            account = note.counter_account
            self.stdout.write(
                f"شركة {note.tenant_id} · {note.note_number} ({note.get_note_type_display()}) · "
                f"{note.note_date} · {note.partner.name} (#{note.partner_id}) · "
                f"{note.amount} {getattr(note.currency, 'Code', '') or ''}".rstrip()
                + f" · المقابل {account.code} {account.name} [{KIND_LABEL[kind]}] · قيد #{note.journal_id}"
            )
        self.stdout.write(
            f"المجموع: {found} إشعار. لا تعديل — صحّحها يدوياً: إلغاء الترحيل ثم تعديل الحساب المقابل."
        )
