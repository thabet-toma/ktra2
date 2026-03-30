import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner
from inventory.models import Product, ProductCategory

def recover_test():
    print("--- TESTING RECOVERY ---")
    try:
        p_count = Partner.objects.count()
        print(f"Partners: {p_count}")
    except Exception as e:
        print(f"Partner error: {e}")

    try:
        prod_count = Product.objects.count()
        print(f"Products: {prod_count}")
    except Exception as e:
        print(f"Product error: {e}")

    try:
        cat_count = ProductCategory.objects.count()
        print(f"Categories: {cat_count}")
    except Exception as e:
        print(f"Category error: {e}")

if __name__ == "__main__":
    recover_test()
