# -*- coding: utf-8 -*-
"""بذر بيانات بحجم واقعي لاختبار الحمل (المرحلة 6 من docs/REFACTOR_PROMPTS.md).

يولّد 3-5 شركات، كلٌّ بشجرة حساباتها وفترتها المالية ومستودعها وأصنافها
وعملائها وآلاف فواتير البيع **المرحّلة** (قيود + حركات مخزون حقيقية) — لأن
اختبار حمل على قاعدة فارغة كذبة: الفهارس لا تُختبر، والتقارير ترجع صفراً،
وخطط الاستعلام تختلف كلياً عن الإنتاج.

كل الكتابة تمرّ بمسارات النظام نفسها (`heal_company_seed` للتأسيس،
`record_stock_movement` للمخزون، `post_sales_invoice` للترحيل، `next_invoice_number`
للترقيم) — لا كتابة مباشرة لقيدٍ أو حركة، فما يُبذَر يطابق ما ينتجه النظام.

════════════ حارس السلامة (يسبق أي كتابة، ويفشل مغلقاً) ════════════
البذر **مدمّر بطبيعته** على قاعدة فيها بيانات مستخدمين. لذلك يرفض الأمر العمل
ما لم تتحقق كل الشروط الآتية:
  1. تمرير `--i-know-what-im-doing` صراحةً.
  2. اسم قاعدة البيانات يحوي `loadtest`/`load_test` (أو يطابق `--expect-db`
     الذي تمرّره أنت حرفياً).
  3. لا توجد في القاعدة أي شركة **ليست** من شركات الحمل (بادئة LOADTEST).
  4. لا يوجد في القاعدة أي مستخدم غير مستخدمي الحمل (عدا السوبر أدمن).
  5. مضيف القاعدة محلي، إلا إذا مُرّر `--allow-remote-db` صراحةً.
النقطتان 3 و4 هما الحارس الحقيقي: علمٌ في سطر الأوامر يُنسى، أما قاعدةٌ فيها
شركة واحدة حقيقية فتوقف الأمر مهما بلغت الأعلام.

الاستخدام:
    python manage.py seed_load_test_data --i-know-what-im-doing \
        --password '<كلمة مرور حسابات الحمل>' \
        --tenants 4 --products 800 --customers 200 --invoices 1500 \
        --manifest load_tests/seed_manifest.json

يكتب ملف بيان (بلا كلمات مرور) يقرأه `load_tests/locustfile.py`.
الأمر idempotent: إعادة تشغيله تُكمل الناقص ولا تُكرّر ما وُجد.
"""
from __future__ import annotations

import json
import os
import random
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

COMPANY_PREFIX = "LOADTEST"
COMPANY_NAME_TEMPLATE = COMPANY_PREFIX + " — شركة {n}"
USER_EMAIL_TEMPLATE = "loadtest+t{n}@ktra.invalid"
SAFE_DB_MARKERS = ("loadtest", "load_test")
LOCAL_DB_HOSTS = ("", "localhost", "127.0.0.1", "::1", "db", "mysql")

BRANDS = ["ألفا", "بيتا", "جاما", "دلتا", "أوميغا", "نوفا", "زينيت", "أطلس"]
CATEGORY_NAMES = [
    "إطارات", "بطاريات", "زيوت", "فلاتر", "قطع كهرباء", "إكسسوارات",
    "أدوات", "مواد استهلاكية",
]
CITIES = ["نابلس", "رام الله", "الخليل", "جنين", "طولكرم", "بيت لحم", "أريحا"]


class Command(BaseCommand):
    help = (
        "يبذر بيانات حمل واقعية (3-5 شركات × آلاف الفواتير/القيود/الأصناف) "
        "— على قاعدة اختبار معزولة فقط."
    )

    # ── الوسائط ────────────────────────────────────────────────────────────
    def add_arguments(self, parser):
        parser.add_argument(
            "--i-know-what-im-doing", action="store_true", dest="ack",
            help="إقرار صريح بأن هذه قاعدة اختبار معزولة (إلزامي).",
        )
        parser.add_argument(
            "--password", required=True,
            help="كلمة مرور حسابات الحمل — لا تُخزَّن في الريبو، مرّرها هنا "
                 "ومرّر نفسها لـlocust عبر KTRA_LOADTEST_PASSWORD.",
        )
        parser.add_argument("--tenants", type=int, default=4, help="عدد الشركات (3-5)")
        parser.add_argument("--products", type=int, default=800, help="أصناف لكل شركة")
        parser.add_argument("--customers", type=int, default=200, help="عملاء لكل شركة")
        parser.add_argument("--suppliers", type=int, default=40, help="موردون لكل شركة")
        parser.add_argument("--invoices", type=int, default=1500, help="فواتير بيع لكل شركة")
        parser.add_argument("--lines-min", type=int, default=2)
        parser.add_argument("--lines-max", type=int, default=6)
        parser.add_argument("--days", type=int, default=540,
                            help="عمق التاريخ بالأيام (يوزَّع تاريخ الفواتير عليه)")
        parser.add_argument("--post-ratio", type=float, default=0.85,
                            help="نسبة الفواتير المرحّلة (الباقي مسودات)")
        parser.add_argument("--seed", type=int, default=20260811, help="بذرة العشوائية")
        parser.add_argument("--expect-db", default=None,
                            help="اسم القاعدة المتوقَّع — يجب أن يطابق DATABASES['default']['NAME']")
        parser.add_argument("--allow-remote-db", action="store_true",
                            help="اسمح بقاعدة على مضيف غير محلي (خطر — لا تستعمله مع الإنتاج)")
        parser.add_argument("--allow-sqlite", action="store_true",
                            help="اسمح بـSQLite (أرقامها لا تمثّل الإنتاج — للتجربة فقط)")
        parser.add_argument("--manifest", default="load_tests/seed_manifest.json",
                            help="مسار ملف البيان الذي يقرأه locust")

    # ── التنفيذ ────────────────────────────────────────────────────────────
    def handle(self, *args, **opt):
        self._guard(opt)

        random.seed(opt["seed"])
        tenants_count = max(3, min(5, opt["tenants"]))
        if tenants_count != opt["tenants"]:
            self.stdout.write(self.style.WARNING(
                f"عدد الشركات صُحّح إلى {tenants_count} (المدى المسموح 3-5)."
            ))

        currency = self._ensure_currency()
        uom = self._ensure_uom()
        manifest = {
            "generated_at": date.today().isoformat(),
            "database": django_settings.DATABASES["default"].get("NAME"),
            "tenants": [],
        }

        for n in range(1, tenants_count + 1):
            entry = self._seed_tenant(n, currency, uom, opt)
            manifest["tenants"].append(entry)

        self._write_manifest(opt["manifest"], manifest)
        self.stdout.write(self.style.SUCCESS(
            f"تم البذر: {tenants_count} شركة — البيان في {opt['manifest']}"
        ))

    # ── الحارس ────────────────────────────────────────────────────────────
    def _guard(self, opt):
        from tenants.models import Tenant

        if not opt["ack"]:
            raise CommandError(
                "مرفوض: هذا الأمر يكتب آلاف السجلات ويُفترض ألا يمسّ إلا قاعدة "
                "اختبار معزولة. مرّر --i-know-what-im-doing إن كنت متأكداً."
            )
        if len(opt["password"] or "") < 8:
            raise CommandError("كلمة المرور قصيرة جداً (8 محارف على الأقل).")

        db = django_settings.DATABASES["default"]
        name = str(db.get("NAME") or "")
        engine = str(db.get("ENGINE") or "")
        host = str(db.get("HOST") or "").strip().lower()

        if opt["expect_db"] and opt["expect_db"] != name:
            raise CommandError(
                f"مرفوض: القاعدة الفعلية «{name}» لا تطابق --expect-db «{opt['expect_db']}». "
                "راجع .env / DJANGO_SETTINGS_MODULE قبل إعادة المحاولة."
            )
        if not opt["expect_db"]:
            marker = any(m in name.lower() for m in SAFE_DB_MARKERS)
            if not marker:
                raise CommandError(
                    f"مرفوض: اسم القاعدة «{name}» لا يحوي loadtest/load_test. "
                    "أنشئ قاعدة مخصّصة للحمل (مثلاً ktra_loadtest) أو مرّر "
                    "--expect-db بنفس الاسم إن كنت متأكداً أنها معزولة."
                )
        if "sqlite" in engine and not opt["allow_sqlite"]:
            raise CommandError(
                "مرفوض: القاعدة SQLite — أرقام الحمل عليها لا تمثّل الإنتاج "
                "(لا تزامن كتابة، خطط استعلام مختلفة). استعمل MySQL، أو مرّر "
                "--allow-sqlite للتجربة الوظيفية فقط."
            )
        if host not in LOCAL_DB_HOSTS and not opt["allow_remote_db"]:
            raise CommandError(
                f"مرفوض: مضيف القاعدة «{host}» ليس محلياً. البذر ضد خادم بعيد "
                "يُشبه بالضبط الخطأ الذي يُتلف الإنتاج. مرّر --allow-remote-db "
                "فقط إن كان هذا خادم اختبار مخصّصاً."
            )

        # الحارس الحقيقي: أي بيانات ليست من صنع هذا الأمر ⇒ توقف.
        foreign_tenants = list(
            Tenant.objects.exclude(CompanyName__startswith=COMPANY_PREFIX)
            .values_list("TenantID", "CompanyName")[:5]
        )
        if foreign_tenants:
            listed = "، ".join(f"#{tid} {cname}" for tid, cname in foreign_tenants)
            raise CommandError(
                "مرفوض: القاعدة تحوي شركات ليست من بيانات الحمل — "
                f"{listed}. هذه ليست قاعدة اختبار معزولة."
            )
        foreign_users = list(
            User.objects.filter(is_superuser=False)
            .exclude(username__startswith="loadtest+")
            .values_list("username", flat=True)[:5]
        )
        if foreign_users:
            raise CommandError(
                "مرفوض: القاعدة تحوي مستخدمين ليسوا من حسابات الحمل — "
                f"{'، '.join(foreign_users)}. لا تبذر فوق بيانات مستخدمين حقيقيين."
            )

    # ── بنية مشتركة ───────────────────────────────────────────────────────
    def _ensure_currency(self):
        from tenants.models import Currency

        currency, _ = Currency.objects.get_or_create(
            Code="ILS",
            defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        return currency

    def _ensure_uom(self):
        from inventory.models import UnitOfMeasure

        uom, _ = UnitOfMeasure.objects.get_or_create(
            code="PCS", defaults={"name_ar": "قطعة", "name_en": "Piece"},
        )
        return uom

    # ── شركة واحدة ────────────────────────────────────────────────────────
    def _seed_tenant(self, n: int, currency, uom, opt) -> dict:
        from accounting.models import Account
        from accounting.services import create_fiscal_year
        from inventory.models import Warehouse
        from tenants.models import Tenant, UserCompanyMembership
        from sales.services import get_or_create_sales_settings

        name = COMPANY_NAME_TEMPLATE.format(n=n)
        tenant, created = Tenant.objects.get_or_create(
            CompanyName=name,
            defaults={
                # Enterprise = بلا حدود خطة (core/plans.py) — وإلا رُفضت الفواتير
                # تحت الحمل بـ«تجاوزت حدّ الخطة» فبدا الرفض كخطأ أداء.
                "SubscriptionPlan": "Enterprise",
                "Status": "Active",
            },
        )
        self.stdout.write(f"[{tenant.TenantID}] {name} — {'جديدة' if created else 'قائمة'}")

        # 1) التأسيس عبر المسار الرسمي (COA + فرع رئيسي + دفاتر + إعدادات)
        call_command("heal_company_seed", tenant=tenant.TenantID, verbosity=0)

        # 2) حساب COGS ورقي تحت «51» (الشجرة القياسية تعطي الأب فقط)
        parent_51 = Account.objects.filter(tenant=tenant, code="51").first()
        if parent_51:
            Account.objects.get_or_create(
                tenant=tenant, code="5101",
                defaults={
                    "name": "تكلفة البضاعة المباعة (COGS)",
                    "account_type": "Expense", "parent": parent_51, "is_active": True,
                },
            )

        # 3) فترات مالية تغطي كل مدى تواريخ الفواتير
        today = date.today()
        start = today - timedelta(days=opt["days"])
        for year in range(start.year, today.year + 1):
            create_fiscal_year(tenant, year)

        # 4) إعدادات المبيعات — تملأ حسابات الذمم/الإيراد/COGS/المخزون تلقائياً
        sales_settings = get_or_create_sales_settings(tenant.TenantID)
        if sales_settings.default_currency_id is None:
            sales_settings.default_currency = currency
            sales_settings.save(update_fields=["default_currency"])

        # 5) مستودع افتراضي
        warehouse, _ = Warehouse.objects.get_or_create(
            tenant=tenant, code="MAIN",
            defaults={"name": "المستودع الرئيسي", "is_default": True},
        )

        # 6) ضريبة مخرجات 16% مربوطة بـ2104 (وإلا فلا أسطر ضريبة في القيود)
        tax_rate = self._ensure_tax_rate(tenant)

        # 7) المستخدم والعضوية
        email = USER_EMAIL_TEMPLATE.format(n=n)
        user = self._ensure_user(email, opt["password"])
        UserCompanyMembership.objects.get_or_create(
            user=user, tenant=tenant,
            defaults={"role": "manager", "is_default": True},
        )

        # 8) الأطراف والأصناف
        categories = self._ensure_categories(tenant)
        customers = self._ensure_partners(tenant, "Customer", opt["customers"])
        self._ensure_partners(tenant, "Supplier", opt["suppliers"])
        products = self._ensure_products(
            tenant, categories, uom, opt["products"], warehouse, start,
        )

        # 9) الفواتير
        invoice_ids = self._ensure_invoices(
            tenant, user, currency, tax_rate, customers, products, warehouse, opt,
        )

        return {
            "tenant_id": tenant.TenantID,
            "company_name": tenant.CompanyName,
            "user_email": email,
            "currency_id": currency.CurrencyID,
            "warehouse_id": warehouse.id,
            "customer_ids": [p.id for p in customers[:100]],
            "product_ids": [p.id for p in products[:200]],
            "invoice_ids": invoice_ids[:200],
        }

    # ── لبنات ─────────────────────────────────────────────────────────────
    def _ensure_tax_rate(self, tenant):
        from accounting.models import Account, TaxRate

        vat_out = Account.objects.filter(tenant=tenant, code="2104").first()
        if vat_out is None:
            return None
        tax_rate, _ = TaxRate.objects.get_or_create(
            tenant=tenant, code="VAT16",
            defaults={
                "name": "ضريبة القيمة المضافة 16%",
                "rate": Decimal("16.00"),
                "tax_account": vat_out,
                "direction": "sales",
                "is_active": True,
            },
        )
        return tax_rate

    def _ensure_user(self, email: str, password: str):
        user = User.objects.filter(username=email).first()
        if user is None:
            user = User.objects.create_user(
                username=email, email=email, password=password,
            )
        else:
            user.set_password(password)
        user.is_active = True
        user.save()
        return user

    def _ensure_categories(self, tenant):
        from accounting.models import Account
        from inventory.models import ProductCategory

        revenue = Account.objects.filter(tenant=tenant, code="4101").first()
        cogs = Account.objects.filter(tenant=tenant, code="5101").first()
        inventory = Account.objects.filter(tenant=tenant, code="1104").first()
        out = []
        for cname in CATEGORY_NAMES:
            category, _ = ProductCategory.objects.get_or_create(
                tenant=tenant, name=cname,
                defaults={
                    "revenue_account": revenue,
                    "cogs_account": cogs,
                    "inventory_account": inventory,
                },
            )
            out.append(category)
        return out

    def _ensure_partners(self, tenant, partner_type: str, target: int):
        from partners.models import Partner

        existing = list(
            Partner.objects.filter(tenant=tenant, partner_type=partner_type).order_by("id")
        )
        missing = target - len(existing)
        if missing > 0:
            label = "عميل" if partner_type == "Customer" else "مورد"
            new_rows = [
                Partner(
                    tenant=tenant,
                    name=f"{label} {len(existing) + i + 1:04d}",
                    partner_type=partner_type,
                    city=random.choice(CITIES),
                    phone=f"059{random.randint(1000000, 9999999)}",
                    # credit_limit=None عمداً: حدّ ائتمان مضبوط يرفض فواتير
                    # الحمل فيبدو الرفض خطأ أداء.
                    credit_limit=None,
                )
                for i in range(missing)
            ]
            Partner.objects.bulk_create(new_rows, batch_size=500)
            existing = list(
                Partner.objects.filter(tenant=tenant, partner_type=partner_type).order_by("id")
            )
            self.stdout.write(f"    أطراف {partner_type}: +{missing} (الإجمالي {len(existing)})")
        return existing

    def _ensure_products(self, tenant, categories, uom, target: int, warehouse, start_date):
        from inventory.models import Product
        from inventory.services import record_stock_movement

        existing = list(Product.objects.filter(tenant=tenant).order_by("id"))
        missing = target - len(existing)
        if missing > 0:
            base = len(existing)
            new_rows = []
            for i in range(missing):
                idx = base + i + 1
                size = f"{random.choice([155, 165, 175, 185, 195, 205])}/{random.choice([55, 60, 65, 70])}/{random.choice([13, 14, 15, 16, 17])}"
                new_rows.append(
                    Product(
                        tenant=tenant,
                        sku=f"LT-{tenant.TenantID}-{idx:06d}",
                        barcode=f"62{tenant.TenantID:02d}{idx:08d}",
                        name_ar=f"صنف {idx:05d} {size}",
                        name_en=f"Item {idx:05d}",
                        variant_group=size,
                        brand=random.choice(BRANDS),
                        category=random.choice(categories),
                        uom=uom,
                        min_stock_level=random.choice([0, 5, 10, 20]),
                        # المخزون السالب مسموح: الحمل يبيع عشوائياً، ورفض
                        # «لا يوجد رصيد» يلوّث معدّل الأخطاء بلا علاقة بالأداء.
                        allow_negative_stock=True,
                        sale_price=Decimal(str(round(random.uniform(20, 600), 2))),
                    )
                )
            Product.objects.bulk_create(new_rows, batch_size=500)
            existing = list(Product.objects.filter(tenant=tenant).order_by("id"))
            self.stdout.write(f"    أصناف: +{missing} (الإجمالي {len(existing)})")

        # رصيد افتتاحي عبر خدمة المخزون (يبني avg_cost وحركة حقيقية)
        opening_date = start_date
        without_stock = [p for p in existing if Decimal(str(p.quantity_on_hand)) <= 0]
        for i, product in enumerate(without_stock, 1):
            record_stock_movement(
                product=product,
                movement_type="IN",
                quantity=Decimal(random.randint(200, 2000)),
                unit_cost=Decimal(str(round(random.uniform(8, 400), 2))),
                reference_type="MANUAL",
                movement_date=opening_date,
                notes="رصيد افتتاحي — بيانات حمل",
                tenant=tenant,
                warehouse=warehouse,
            )
            if i % 200 == 0:
                self.stdout.write(f"      رصيد افتتاحي: {i}/{len(without_stock)}")
        return existing

    def _ensure_invoices(
        self, tenant, user, currency, tax_rate, customers, products, warehouse, opt,
    ) -> list[int]:
        from sales.models import SalesInvoice, SalesInvoiceLine
        from sales.services import next_invoice_number, post_sales_invoice

        existing_ids = list(
            SalesInvoice.objects.filter(tenant=tenant)
            .order_by("-id").values_list("id", flat=True)[:400]
        )
        existing_count = SalesInvoice.objects.filter(tenant=tenant).count()
        missing = opt["invoices"] - existing_count
        if missing <= 0:
            self.stdout.write(f"    فواتير: {existing_count} (مكتملة)")
            return list(existing_ids)

        today = date.today()
        span = max(1, opt["days"])
        created_ids: list[int] = []
        failures = 0
        for i in range(missing):
            invoice_date = today - timedelta(days=random.randint(0, span))
            customer = random.choice(customers)
            try:
                with transaction.atomic():
                    invoice = SalesInvoice.objects.create(
                        tenant=tenant,
                        invoice_number=next_invoice_number(tenant.TenantID),
                        customer=customer,
                        invoice_date=invoice_date,
                        due_date=invoice_date + timedelta(days=30),
                        invoice_type=random.choice(
                            [SalesInvoice.INVOICE_CASH, SalesInvoice.INVOICE_CREDIT]
                        ),
                        currency=currency,
                        created_by=user,
                    )
                    lines = []
                    for _ in range(random.randint(opt["lines_min"], opt["lines_max"])):
                        product = random.choice(products)
                        lines.append(
                            SalesInvoiceLine(
                                tenant=tenant,
                                invoice=invoice,
                                product=product,
                                quantity=Decimal(random.randint(1, 8)),
                                unit_price=Decimal(str(product.sale_price or 50)),
                                tax_rate=tax_rate,
                                warehouse=warehouse.name,
                            )
                        )
                    SalesInvoiceLine.objects.bulk_create(lines)
                if random.random() < opt["post_ratio"]:
                    post_sales_invoice(invoice, user=user)
                created_ids.append(invoice.id)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                if failures <= 5:
                    self.stderr.write(f"      فشل ترحيل فاتورة: {exc}")
                elif failures == 6:
                    self.stderr.write("      … (تُكتم بقية رسائل الفشل)")
            if (i + 1) % 100 == 0:
                self.stdout.write(f"      فواتير: {i + 1}/{missing}")

        self.stdout.write(
            f"    فواتير: +{len(created_ids)} (فشل {failures}) — "
            f"الإجمالي {existing_count + len(created_ids)}"
        )
        return (created_ids + list(existing_ids))[:400]

    # ── البيان ────────────────────────────────────────────────────────────
    def _write_manifest(self, path: str, manifest: dict) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
