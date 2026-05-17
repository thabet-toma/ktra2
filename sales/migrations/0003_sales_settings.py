import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0013_seed_import_accounts_and_fix_vat"),
        ("partners", "0003_alter_partner_createdat_and_more"),
        ("sales", "0002_fix_payment_currency_mismatch"),
        ("tenants", "0002_alter_currency_options_alter_tenant_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesSettings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        db_column="SalesSettingsID",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "default_payment_type",
                    models.CharField(
                        choices=[("cash", "نقدي"), ("credit", "آجل")],
                        db_column="DefaultPaymentType",
                        default="credit",
                        max_length=20,
                    ),
                ),
                (
                    "stock_on_post_default",
                    models.BooleanField(
                        db_column="StockOnPostDefault",
                        default=True,
                        help_text="خصم المخزون الافتراضي عند الترحيل",
                    ),
                ),
                (
                    "prices_include_tax",
                    models.BooleanField(
                        db_column="PricesIncludeTax",
                        default=False,
                        help_text="إذا كان مفعّلاً، تُعامل الأسعار المدخلة كشاملة للضريبة",
                    ),
                ),
                (
                    "auto_post_invoices",
                    models.BooleanField(
                        db_column="AutoPostInvoices",
                        default=False,
                        help_text="ترحيل تلقائي للفواتير بعد الحفظ",
                    ),
                ),
                (
                    "show_journal_preview",
                    models.BooleanField(
                        db_column="ShowJournalPreview",
                        default=True,
                        help_text="إظهار معاينة القيد المحاسبي قبل الترحيل",
                    ),
                ),
                (
                    "default_shipping_origin",
                    models.CharField(
                        blank=True,
                        db_column="DefaultShippingOrigin",
                        default="",
                        max_length=200,
                    ),
                ),
                (
                    "default_shipping_destination",
                    models.CharField(
                        blank=True,
                        db_column="DefaultShippingDestination",
                        default="",
                        max_length=200,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, db_column="UpdatedAt")),
                (
                    "default_customer",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultCustomerID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="default_for_sales_settings",
                        to="partners.partner",
                    ),
                ),
                (
                    "default_currency",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultCurrencyID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="default_sales_settings",
                        to="tenants.currency",
                        to_field="CurrencyID",
                    ),
                ),
                (
                    "default_revenue_account_product",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultRevenueAccountProductID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_settings_rev_product",
                        to="accounting.account",
                    ),
                ),
                (
                    "default_revenue_account_service",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultRevenueAccountServiceID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_settings_rev_service",
                        to="accounting.account",
                    ),
                ),
                (
                    "default_cash_account",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultCashAccountID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_settings_cash",
                        to="accounting.account",
                    ),
                ),
                (
                    "default_inventory_account",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultInventoryAccountID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_settings_inventory",
                        to="accounting.account",
                    ),
                ),
                (
                    "default_cogs_account",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultCogsAccountID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_settings_cogs",
                        to="accounting.account",
                    ),
                ),
                (
                    "default_ar_account",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultArAccountID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_settings_ar",
                        to="accounting.account",
                    ),
                ),
                (
                    "default_vat_rate",
                    models.ForeignKey(
                        blank=True,
                        db_column="DefaultVatRateID",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_settings_vat",
                        to="accounting.taxrate",
                    ),
                ),
                (
                    "tenant",
                    models.OneToOneField(
                        db_column="TenantID",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sales_settings",
                        to="tenants.tenant",
                        to_field="TenantID",
                    ),
                ),
            ],
            options={
                "db_table": "sales_module_settings",
                "managed": True,
            },
        ),
    ]
