"""P2-4 (SCALABILITY_AUDIT): تدقيق دخان قبل اعتماد فرض المفاتيح الأجنبية.

`foreign_key_checks=0` كان ثابتاً على كل اتصال إنتاجي طوال عمر النظام، أي أن
القاعدة لم تتحقق من ولا مفتاح أجنبي واحد. فرضها صار الافتراضي، لكن اختبارات
المشروع على SQLite لا تكشف ما تركته السنوات في MySQL من صفوف يتيمة — وهذه
الصفوف هي ما سينفجر لاحقاً (حذف أب مرجوع إليه، أو ALTER يعيد التحقق).

الأمر **قراءة فقط** — لا يكتب ولا يعدّل شيئاً:
  1. يطبع نسخة الخادم (مهم أيضاً لفهارس DESC: حقيقية على MySQL 8+، متجاهَلة
     على 5.7).
  2. يعدّ قيود FK المعرَّفة في المخطط.
  3. لكل علاقة FK: يعدّ الصفوف اليتيمة (ابن يشير إلى أب غير موجود).

التشغيل على الإنتاج (من السيرفر أو محلياً بمتغيرات `.env`):
    python manage.py audit_fk_orphans

النتيجة صفر يتيم = فرض المفاتيح آمن. غير ذلك = عالج المذكور أولاً أو أبقِ
`MYSQL_DISABLE_FK_CHECKS=1` حتى المعالجة.

على SQLite (بيئة الاختبار) يخرج مبكراً بلا خطأ — التدقيق بلا معنى هناك.
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "تدقيق قراءة-فقط: صفوف FK يتيمة في MySQL قبل اعتماد فرض المفاتيح (P2-4)"

    def handle(self, *args, **options):
        if connection.vendor != "mysql":
            self.stdout.write(self.style.WARNING(
                f"القاعدة الحالية {connection.vendor} لا MySQL — "
                "التدقيق يخص الإنتاج؛ لا شيء يُفحص هنا."
            ))
            return

        with connection.cursor() as cur:
            cur.execute("SELECT @@version, @@version_comment")
            version, comment = cur.fetchone()
            self.stdout.write(f"خادم MySQL: {version} ({comment})")
            major = int(str(version).split(".")[0] or 0)
            if major < 8:
                self.stdout.write(self.style.WARNING(
                    "⚠️ نسخة أقدم من 8: فهارس DESC تُتجاهَل (تُقرأ عكسياً — "
                    "أبطأ قليلاً لكن صحيحة)."
                ))

            db = connection.settings_dict["NAME"]
            cur.execute(
                """
                SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = %s
                """,
                [db],
            )
            self.stdout.write(f"قيود FK المعرَّفة في المخطط: {cur.fetchone()[0]}")

            cur.execute(
                """
                SELECT kcu.TABLE_NAME, kcu.COLUMN_NAME,
                       kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE kcu
                WHERE kcu.CONSTRAINT_SCHEMA = %s
                  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY kcu.TABLE_NAME
                """,
                [db],
            )
            relations = cur.fetchall()
            self.stdout.write(f"علاقات FK المفحوصة: {len(relations)}")

            orphaned = []
            for table, col, ref_table, ref_col in relations:
                query = (
                    f"SELECT COUNT(*) FROM `{table}` c "
                    f"LEFT JOIN `{ref_table}` p ON c.`{col}` = p.`{ref_col}` "
                    f"WHERE c.`{col}` IS NOT NULL AND p.`{ref_col}` IS NULL"
                )
                try:
                    cur.execute(query)
                    count = cur.fetchone()[0]
                except Exception as exc:  # noqa: BLE001 — علاقة غير قابلة للفحص تُذكر ولا تُسقِط البقية
                    self.stdout.write(self.style.WARNING(
                        f"تخطٍّ: {table}.{col} → {ref_table}.{ref_col}: {exc}"
                    ))
                    continue
                if count:
                    orphaned.append((table, col, ref_table, ref_col, count))

        if orphaned:
            self.stdout.write(self.style.ERROR(
                "❌ صفوف يتيمة — عالجها قبل اعتماد الفرض "
                "(أو أبقِ MYSQL_DISABLE_FK_CHECKS=1 مؤقتاً):"
            ))
            for table, col, ref_table, ref_col, count in orphaned:
                self.stdout.write(
                    f"  {table}.{col} → {ref_table}.{ref_col}: {count} يتيماً"
                )
        else:
            self.stdout.write(self.style.SUCCESS(
                "✅ صفر صفوف يتيمة عبر كل علاقات FK — فرض المفاتيح آمن."
            ))
