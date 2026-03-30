import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner
from inventory.models import Product, ProductCategory

def test_queries():
    print("--- Testing Partners ---")
    try:
        count = Partner.objects.count()
        print(f"Partner count: {count}")
    except Exception as e:
        print(f"Partner query error: {e}")

    print("\n--- Testing Products ---")
    try:
        count = Product.objects.count()
        print(f"Product count: {count}")
    except Exception as e:
        print(f"Product query error: {e}")

    print("\n--- Testing Categories ---")
    try:
        count = ProductCategory.objects.count()
        print(f"Category count: {count}")
    except Exception as e:
        print(f"Category query error: {e}")

if __name__ == "__main__":
    test_queries()
