import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner

def test_fetch():
    try:
        print("Fetching partners...")
        partners = Partner.objects.all()
        count = partners.count()
        print(f"Count: {count}")
        if count > 0:
            for p in partners[:2]:
                print(f"ID: {p.id}, Name: {p.name}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_fetch()
