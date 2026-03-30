import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

def apply_sql_file(file_path):
    """تطبيق ملف SQL على قاعدة البيانات"""
    print(f"Reading SQL file: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # تقسيم الأوامر على أساس الفاصلة المنقوطة
    # ملاحظة: هذا بسيط ولا يتعامل مع كل الحالات المعقدة
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
    
    with connection.cursor() as cursor:
        for i, statement in enumerate(statements, 1):
            # تنظيف التعليقات من بداية الجملة البرمجية
            clean_stmt = statement
            while clean_stmt and (clean_stmt.strip().startswith('--') or clean_stmt.strip().startswith('/*')):
                # إزالة السطر الأول لو كان تعليقاً
                lines = clean_stmt.split('\n', 1)
                if len(lines) > 1:
                    clean_stmt = lines[1]
                else:
                    clean_stmt = ""
            
            clean_stmt = clean_stmt.strip()
            
            if not clean_stmt or clean_stmt.startswith('USE'):
                continue
                
            try:
                print(f"\n[{i}] Executing statement...")
                print(f"{clean_stmt[:100]}..." if len(clean_stmt) > 100 else clean_stmt)
                cursor.execute(clean_stmt)
                print(f"[OK] Success!")
            except Exception as e:
                print(f"[ERROR] {e}")
                # نستمر في تنفيذ باقي الأوامر حتى لو فشل أحدها

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_sql_file.py <path_to_sql_file>")
        sys.exit(1)
    
    sql_file = sys.argv[1]
    
    if not os.path.exists(sql_file):
        print(f"Error: File not found: {sql_file}")
        sys.exit(1)
    
    apply_sql_file(sql_file)
    print("\n[DONE] SQL file execution completed!")
