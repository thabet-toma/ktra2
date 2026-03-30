import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner, PartnerBankAccount

print("--- فحص الشركاء والحسابات البنكية ---")
partners = Partner.objects.all()
if not partners.exists():
    print("لا يوجد شركاء في قاعدة البيانات.")
else:
    for p in partners:
        accounts = p.bank_accounts.all()
        print(f"الشريك: {p.Name} (ID: {p.PartnerID})")
        if not accounts.exists():
            print("  - لا يوجد حسابات بنكية مسجلة.")
        else:
            for acc in accounts:
                print(f"  - بنك: {acc.BankName} | رقم: {acc.AccountNumber} | عملة: {acc.Currency.Code if acc.Currency else 'غير محددة'}")
print("--- انتهى الفحص ---")
