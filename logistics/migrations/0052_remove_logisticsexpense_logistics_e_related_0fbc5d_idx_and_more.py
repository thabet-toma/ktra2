# D3 (import redesign M6): drop LogisticsExpense.
#
# Production schema drift: the `logistics_expenses` table exists but the named
# index `logistics_e_Related_0fbc5d_idx` was never created there (legacy tables
# don't match migration-history index names — see PROJECT_MAP pinned rule). So the
# auto-generated RemoveIndex step fails. We instead update Django's migration STATE
# (remove the index + model) while the DATABASE operation is a single idempotent
# `DROP TABLE IF EXISTS`, which removes the table and all its indexes regardless of
# how they were named — and is a no-op if the table was already gone.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0051_backfill_stage_and_chargeable_unit'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name='logisticsexpense',
                    name='logistics_e_Related_0fbc5d_idx',
                ),
                migrations.DeleteModel(
                    name='LogisticsExpense',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS logistics_expenses",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
