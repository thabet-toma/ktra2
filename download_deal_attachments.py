import os
import django
import requests
from urllib.parse import urlparse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from core.models import SystemAttachment

def main():
    target_dir = r"C:\Users\asus\Desktop\ملفات_الصفقات"
    os.makedirs(target_dir, exist_ok=True)
    
    atts = SystemAttachment.objects.filter(related_table='logistics_deals')
    total = atts.count()
    print(f"Found {total} deal attachments.")
    
    success = 0
    failed = 0
    
    for att in atts:
        url = att.file_path
        if not url.startswith('http'):
            print(f"Skipping {att.id} - not a valid URL: {url}")
            continue
            
        try:
            # Extract filename from URL
            parsed = urlparse(url)
            basename = os.path.basename(parsed.path)
            if not basename:
                basename = f"attachment_{att.id}"
                
            # Prepend deal id for clarity
            filename = f"Deal_{att.related_id}_{basename}"
            
            # Remove any dangerous characters just in case
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_', '-'))
            
            filepath = os.path.join(target_dir, filename)
            
            print(f"Downloading {url} -> {filename}")
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            success += 1
        except Exception as e:
            print(f"Failed to download {url}: {e}")
            failed += 1
            
    print(f"\nDone! Successfully downloaded {success} files. Failed: {failed}.")
    print(f"Files saved in: {target_dir}")

if __name__ == '__main__':
    main()
