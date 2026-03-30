import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner

try:
    print(f"Total partners found in DB: {Partner.objects.count()}")
    partners = list(Partner.objects.all()[:5])
    print(f"Successfully fetched {len(partners)} partners from DB.")
    for p in partners:
        print(f"Partner: {p.name}")
except Exception as e:
    print(f"Error: {str(e)}")
