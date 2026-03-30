import os
import django
from django.core.management import call_command
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings') # it's usually core.settings or ktra.settings
try:
    if not os.path.exists('core/settings.py'):
        # Just fallback to searching for settings if it's not core.settings
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
    django.setup()
    print("Django loaded successfully. Running makemigrations...")
    with open("migration_log.txt", "w", encoding="utf-8") as f:
        f.write("Starting migrations...\n")
    
    call_command('makemigrations', 'logistics')
    call_command('migrate', 'logistics')
    
    with open("migration_log.txt", "a", encoding="utf-8") as f:
        f.write("Migrations completed successfully!\n")
        
except Exception as e:
    with open("migration_error.txt", "w", encoding="utf-8") as f:
        f.write(traceback.format_exc())
