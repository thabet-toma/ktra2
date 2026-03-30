import os
import django
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

print("Testing Cloudinary storage backend...")
try:
    path = default_storage.save('test_file.txt', ContentFile('hello world'))
    print(f"Successfully saved to: {path}")
    url = default_storage.url(path)
    print(f"URL: {url}")
except Exception as e:
    print(f"FAILED: {e}")
