import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner
from partners.serializers import PartnerSerializer

try:
    partners = Partner.objects.all()[:5]
    print(f"Total partners found in DB: {Partner.objects.count()}")
    serializer = PartnerSerializer(partners, many=True)
    data = serializer.data
    print("Serialization successful.")
    print(f"Sample data length: {len(data)}")
    if data:
        print(f"First partner attachments: {data[0].get('attachments')}")
except Exception as e:
    print(f"Error during serialization: {str(e)}")
    import traceback
    traceback.print_exc()
