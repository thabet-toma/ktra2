import datetime
import logging

from django.db import models
from tenants.models import Tenant, Currency
from core.base_models import SoftDeleteMixin, TimeStampMixin
from partners.models import Partner
from .account_classification import SUB_TYPE_CHOICES, sub_type_for_account

logger = logging.getLogger(__name__)

class CostCenter(models.Model):
    id = models.AutoField(primary_key=True, db_column='CostCenterID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    name = models.CharField(max_length=150, db_column='Name')
    code = models.CharField(max_length=50, null=True, blank=True, db_column='Code')
    description = models.TextField(null=True, blank=True, db_column='Description')

    class Meta:
        db_table = 'cost_centers'
        managed = True
        unique_together = [['tenant', 'name']]

    def __str__(self):
        return self.name

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('Asset', 'Asset'),
        ('Liability', 'Liability'),
        ('Equity', 'Equity'),
        ('Revenue', 'Revenue'),
        ('Expense', 'Expense'),
    ]

    NATURE_DEBIT_ONLY = 'debit_only'
    NATURE_CREDIT_ONLY = 'credit_only'
    NATURE_BOTH = 'both'
    NATURE_CHOICES = [
        (NATURE_DEBIT_ONLY, 'مدين فقط'),
        (NATURE_CREDIT_ONLY, 'دائن فقط'),
        (NATURE_BOTH, 'مدين/دائن'),
    ]

    id = models.AutoField(primary_key=True, db_column='AccountID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    code = models.CharField(max_length=20, null=True, blank=True, db_column='Code')
    name = models.CharField(max_length=100, null=True, blank=True, db_column='Name')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, db_column='ParentID', related_name='children')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, null=True, blank=True, db_column='Type')
    # THA-111: الغرض الوظيفي للحساب — «صندوق» و«ذمم عملاء» و«مخزون» كلها
    # `Asset`، فكان كل منتقي حساب يخمّن الغرض ببادئة الرقم أو بالاسم ويصل إلى
    # إجابات متضاربة. NULL = حساب عادي يكفيه `account_type`. مفصول عن
    # `ACCOUNT_TYPES` عمداً: تلك الخمسة تقود الطبيعة والحساب الختامي والتقارير،
    # وإضافة قيمة إليها تكسرها بصمت. الاشتقاق في `account_classification.py`.
    sub_type = models.CharField(
        max_length=20, choices=SUB_TYPE_CHOICES, null=True, blank=True,
        db_column='SubType',
        help_text='التصنيف الوظيفي: صندوق/بنك/ذمم مدينة/ذمم دائنة/مخزون. فارغ = حساب عادي.',
    )
    nature = models.CharField(
        max_length=20, choices=NATURE_CHOICES, null=True, blank=True,
        db_column='Nature',
        help_text='طبيعة الحساب: مدين فقط / دائن فقط / مدين ودائن. تُفرَض على القيود.',
    )
    is_active = models.BooleanField(default=True, db_column='IsActive')
    default_cost_center = models.ForeignKey(
        'CostCenter', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='DefaultCostCenterID', related_name='accounts_with_default',
        help_text='مركز التكلفة الافتراضي للحساب — يُملأ تلقائياً في القيود',
    )
    notes = models.TextField(null=True, blank=True, db_column='Notes',
        help_text='ملاحظات الحساب — تُعرض عند F4 drill-down',
    )

    class Meta:
        db_table = 'chartofaccounts'
        managed = True
        unique_together = [['tenant', 'code']]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        """يشتقّ التصنيف الوظيفي عند الإنشاء وحده، وبلا أن يعترض طريق الحفظ.

        نقطةٌ واحدة عمداً بدل ترقيع كل موضع يُنشئ حساباً (بذر شجرة شركة، حساب
        الطرف التلقائي، الحساب التشغيلي، الـAPI): مسارٌ جديد يُضاف غداً يرث
        الاشتقاق بلا أن يتذكّره أحد. الاشتقاق لا يعمل إلا حين يكون التصنيف
        فارغاً، فالتصحيح اليدوي من بطاقة الحساب — وأي تصنيف صريح — يبقى أقوى
        منه، وتحديث حسابٍ قائم لا يعيد فتح ما استقرّ.
        """
        if self._state.adding and not self.sub_type:
            try:
                self.sub_type = sub_type_for_account(self)
            except Exception:  # noqa: BLE001 — تصنيفٌ فاشل لا يمنع إنشاء حساب
                logger.exception(
                    "account.sub_type derivation failed for code=%s", self.code,
                )
        super().save(*args, **kwargs)

class JournalHeader(models.Model):
    id = models.AutoField(primary_key=True, db_column='JournalID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    # task11 M4: NULL = قيد على مستوى الشركة/الفرع الرئيسي؛ قيمة = قيد فرع
    # (يغذي تقارير P&L/ميزان المراجعة المستقلة لكل فرع)
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.PROTECT, null=True, blank=True,
        db_column='BranchID', related_name='journal_headers')
    transaction_date = models.DateField(null=True, blank=True, db_column='TransactionDate')
    reference_type = models.CharField(max_length=50, null=True, blank=True, db_column='ReferenceType')
    reference_id = models.IntegerField(null=True, blank=True, db_column='ReferenceID')
    description = models.TextField(null=True, blank=True, db_column='Description')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True,
        db_column='CurrencyID', related_name='journal_headers',
    )
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=1.0, db_column='ExchangeRate',
    )
    # A3: مَن أنشأ القيد — دفتر اليومية يُصفَّى بالمستخدم، والمحاسب يعرف صاحب
    # كل قيد. NULL = قيود ما قبل هذا العمود، أو قيد ولّده مسار آلي بلا مستخدم.
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy_UserID',
    )

    class Meta:
        db_table = 'journal_headers'
        managed = True
        # m3-03 ملغى عمداً: قيد فريد على (tenant, reference_type, reference_id)
        # غير ممكن هنا — MySQL لا يدعم الفهارس الجزئية (partial unique) فيُتجاهَل
        # بصمت، كما أن المجال نفسه غير فريد فعلياً (69 صفقة لكلٍّ قيدان مشروعان
        # بنوع LOGISTICS_DEAL). idempotency مفروض تطبيقياً في C1-13/C1-17/C1-04.
        # صيانة الأداء 2026-07: حقول الفلترة/الترتيب غير المفهرسة (الـ FKs مفهرسة
        # تلقائياً) — فهارس مركّبة تبدأ بـ tenant لأن كل الاستعلامات tenant-scoped.
        indexes = [
            models.Index(fields=['tenant', 'transaction_date', 'id'],
                         name='idx_jh_tenant_date_id'),
            models.Index(fields=['tenant', 'reference_type', 'reference_id'],
                         name='idx_jh_tenant_ref'),
            models.Index(fields=['tenant', 'is_posted'],
                         name='idx_jh_tenant_posted'),
        ]

    def __str__(self):
        return f"Journal {self.id} - {self.transaction_date}"

    def save(self, *args, **kwargs):
        """منع تعديل أو حذف قيد مرحّل على مستوى الموديل."""
        if self.pk:
            try:
                old = JournalHeader.objects.only('is_posted').get(pk=self.pk)
                if old.is_posted:
                    from django.core.exceptions import ValidationError as DjangoVE
                    raise DjangoVE("لا يمكن تعديل قيد مرحّل. أنشئ قيداً عكسياً بدلاً من ذلك.")
            except JournalHeader.DoesNotExist:
                pass
        super().save(*args, **kwargs)

class JournalLine(models.Model):
    id = models.AutoField(primary_key=True, db_column='JLineID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    journal = models.ForeignKey(JournalHeader, on_delete=models.CASCADE, db_column='JournalID', related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, db_column='AccountID')
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='Debit')
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='Credit')

    # ── Base Currency Equivalents (auto-calculated on save) ──
    # Always stores the amount in the tenant's base currency.
    # Formula: base_debit = debit × exchange_rate (from JournalHeader)
    base_debit = models.DecimalField(
        max_digits=18, decimal_places=2, default=0.00, db_column='BaseDebit',
        help_text='مبلغ المدين بالعملة الأساسية = debit × سعر الصرف',
    )
    base_credit = models.DecimalField(
        max_digits=18, decimal_places=2, default=0.00, db_column='BaseCredit',
        help_text='مبلغ الدائن بالعملة الأساسية = credit × سعر الصرف',
    )

    # Updated to Strict Foreign Keys
    partner = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, blank=True, db_column='PartnerID')
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, db_column='CostCenterID')
    description = models.CharField(max_length=500, null=True, blank=True, db_column='LineDescription')
    project_id = models.IntegerField(null=True, blank=True, db_column='ProjectID')

    class Meta:
        db_table = 'journal_lines'
        managed = True
        # صيانة الأداء 2026-07: كشوف الحساب/الميزان تفلتر (tenant, account) معاً.
        # المرحلة 5 / P0-11 (SCALABILITY_AUDIT §3): أكبر جدول محاسبي كان بفهرس
        # واحد، فتقرير أرصدة الشركاء (أثقل تجميع في النظام) = full scan.
        indexes = [
            models.Index(fields=['tenant', 'account'],
                         name='idx_jl_tenant_account'),
            # أرصدة الشركاء وكشف حساب الشريك: core/reports/financial.py
            # (تجميع debit/credit لكل شريك على كل أسطر الشركة).
            models.Index(fields=['tenant', 'partner'],
                         name='idx_jl_tenant_partner'),
            # ضمّ الأسطر إلى رؤوسها في تجميعات الميزان: accounting/views.py:735+.
            models.Index(fields=['tenant', 'journal'],
                         name='idx_jl_tenant_journal'),
            # دفتر الأستاذ لحساب داخل مدى قيود: accounting/views.py:650-655.
            # ملاحظة للمتابعة: هذا يجعل idx_jl_tenant_account بادئةً صارمة منه
            # ⇒ مرشّح للحذف في بند لاحق (توفير كلفة كتابة على أسخن مسار كتابة
            # في النظام). لم يُحذف هنا لأن نطاق البند «إضافة ما حدّده التدقيق».
            models.Index(fields=['tenant', 'account', 'journal'],
                         name='idx_jl_tenant_acc_jrn'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0),
                name='journal_line_debit_non_negative',
            ),
            models.CheckConstraint(
                condition=models.Q(credit__gte=0),
                name='journal_line_credit_non_negative',
            ),
        ]

    def save(self, *args, **kwargs):
        """Auto-calculate base currency amounts from JournalHeader exchange_rate.

        The base amounts feed every base-currency report and the trial balance,
        so an unresolved/invalid rate must fail loudly rather than silently
        defaulting to 1 (which would store base == nominal for foreign-currency
        lines and corrupt all base-currency reporting).
        """
        from decimal import Decimal

        from django.core.exceptions import ValidationError

        if self.journal_id:
            if self._state.adding or not self._meta.get_field("journal").is_cached(self):
                jr = JournalHeader.objects.filter(pk=self.journal_id).values_list(
                    "exchange_rate", flat=True
                ).first()
            else:
                jr = self.journal.exchange_rate
            if jr is None:
                raise ValidationError(
                    f"تعذّر تحديد سعر صرف القيد للسطر (journal_id={self.journal_id}); "
                    "لا يمكن حساب المبلغ بالعملة الأساسية."
                )
            rate = Decimal(str(jr))
            if rate <= 0:
                raise ValidationError(
                    f"سعر صرف القيد غير صالح ({rate}) للقيد journal_id={self.journal_id}."
                )
        else:
            rate = Decimal("1")

        self.base_debit = (Decimal(str(self.debit or 0)) * rate).quantize(Decimal("0.01"))
        self.base_credit = (Decimal(str(self.credit or 0)) * rate).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


class VoidedJournal(models.Model):
    """سلّة المحذوفات لأرقام القيود — «recycle bin» يحجز رقم القيد المحذوف.

    عند التراجع عن ترحيل مستند (إلغاء الترحيل) بوضع recycle، يُحذف القيد الحيّ
    من `journal_headers` (فلا يمسّ أي تقرير) ويُسجَّل رقمه الأصلي هنا. الرقم يبقى
    محجوزاً تلقائياً لأن AutoField لا يعيد استخدام رقم محذوف أبداً؛ هذا الجدول
    يجعل الحجز صريحاً وقابلاً للاسترجاع: عند إعادة الترحيل يُعاد إدراج القيد
    بنفس الرقم الأصلي ثم تُحذف هذه السطر. مخفيّ تماماً عن واجهة المستخدم وكل
    تقارير الأستاذ/ميزان المراجعة (ليس قيداً حيّاً — لا أسطر له).
    """
    id = models.AutoField(primary_key=True, db_column='VoidedJournalID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    original_journal_id = models.IntegerField(
        db_column='OriginalJournalID',
        help_text='رقم القيد (JournalID) الأصلي المحجوز لإعادة الاستخدام عند إعادة الترحيل.',
    )
    reference_type = models.CharField(max_length=50, db_column='ReferenceType')
    reference_id = models.IntegerField(db_column='ReferenceID')
    transaction_date = models.DateField(null=True, blank=True, db_column='TransactionDate')
    description = models.TextField(null=True, blank=True, db_column='Description')
    voided_at = models.DateTimeField(auto_now_add=True, db_column='VoidedAt')
    voided_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='VoidedByUserID', related_name='voided_journals',
    )

    class Meta:
        db_table = 'voided_journals'
        managed = True
        constraints = [
            # حجز واحد فعّال لكل مستند — إعادة الترحيل تستهلك السطر فلا يتراكم.
            models.UniqueConstraint(
                fields=['tenant', 'reference_type', 'reference_id'],
                name='uniq_voided_journal_per_document',
            ),
        ]

    def __str__(self):
        return f"VoidedJournal #{self.original_journal_id} ({self.reference_type}:{self.reference_id})"


class Cheque(models.Model):
    DIRECTION_CHOICES = [
        ('Incoming', 'Incoming'), # From Customer
        ('Outgoing', 'Outgoing'), # To Supplier
    ]
    # CHQ-1: رموز الحالات القديمة لا تتغير أبداً (صفوف مال حية تحملها)، وتُضاف
    # ثلاث حالات فقط. التسمية العربية تختلف حسب الاتجاه — الصادر يقرأ
    # `Under_Collection` بمعنى «مسلَّم» و`Collected` بمعنى «مصروف».
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Received', 'Received'),          # وارد: الورقة في المحفظة، لم تُودَع
        ('Under_Collection', 'Under Collection'),
        ('Collected', 'Collected'),
        ('Bounced', 'Bounced'),
        ('Returned', 'Returned'),
        ('Settled', 'Settled'),
        ('Endorsed', 'Endorsed'),          # وارد: ظُهِّر لطرف ثالث
        ('Cancelled', 'Cancelled'),        # صادر: أُلغي/أُوقف قبل صرفه
    ]

    id = models.AutoField(primary_key=True, db_column='ChequeID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    cheque_number = models.CharField(max_length=50, db_column='ChequeNumber')
    # T-BANKS: البنك المسحوب عليه صار كياناً مستقلاً؛ الحقول النصية تبقى
    # لقطة (snapshot) للشيكات القديمة ولأي بنك غير مسجَّل.
    bank = models.ForeignKey(
        'Bank', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='BankID', related_name='cheques',
        help_text='البنك المسحوب عليه الشيك',
    )
    bank_branch_ref = models.ForeignKey(
        'BankBranch', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='BankBranchID', related_name='cheques',
        help_text='فرع البنك المسحوب عليه',
    )
    deposit_bank_account = models.ForeignKey(
        'BankAccount', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='DepositBankAccountID', related_name='cheques',
        help_text='حساب الشركة البنكي الذي أُودع/صُرف منه الشيك',
    )
    bank_name = models.CharField(max_length=100, null=True, blank=True, db_column='BankName')
    account_number = models.CharField(max_length=50, null=True, blank=True, db_column='AccountNumber')
    bank_branch = models.CharField(max_length=100, null=True, blank=True, db_column='BankBranch')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount', default=0.00)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, default=1, db_column='CurrencyID')
    due_date = models.DateField(db_column='DueDate', null=True, blank=True)
    issue_date = models.DateField(null=True, blank=True, db_column='IssueDate')
    payee_name = models.CharField(max_length=150, null=True, blank=True, db_column='PayeeName')
    partner = models.ForeignKey(Partner, on_delete=models.RESTRICT, null=True, blank=True, db_column='PartnerID')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Draft', db_column='Status')
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, db_column='Direction', default='Incoming')
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, db_column='CreatedBy_UserID')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    # M2-T3: link to sales invoice + customer payment
    sales_invoice = models.ForeignKey(
        'sales.SalesInvoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='SalesInvoiceID',
        related_name='cheques',
    )
    customer_payment = models.ForeignKey(
        'sales.CustomerPayment',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='CustomerPaymentID',
        related_name='cheques',
    )
    # T-ONEPAY: شيك صادر داخل سند صرف (مرآة customer_payment للجانب الدائن).
    supplier_payment = models.ForeignKey(
        'sales.SupplierPayment',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='SupplierPaymentID',
        related_name='cheques',
    )
    # CHQ-1: المستفيد من التظهير — الشيك الوارد يُسدَّد به مورد بدل النقد،
    # فتنخفض ذمته بقيد مدين ذممه ÷ دائن «شيكات في المحفظة».
    endorsed_to = models.ForeignKey(
        Partner, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='EndorsedToPartnerID', related_name='endorsed_cheques',
        help_text='الطرف الذي ظُهِّر له الشيك',
    )
    # P-H-1: link to purchase invoice (mirror of sales_invoice)
    purchase_invoice = models.ForeignKey(
        'logistics.PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='PurchaseInvoiceID',
        related_name='cheques',
    )

    class Meta:
        db_table = 'cheques'
        managed = True

    def save(self, *args, **kwargs):
        """T-BANKS: لقطة اسم البنك/الفرع من السجل المرتبط للعرض التاريخي."""
        if self.bank_id and not (self.bank_name or '').strip():
            self.bank_name = (self.bank.name or '')[:100]
        if self.bank_branch_ref_id and not (self.bank_branch or '').strip():
            self.bank_branch = (self.bank_branch_ref.name or '')[:100]
        super().save(*args, **kwargs)

    # CHQ-1: `VALID_TRANSITIONS` و`change_status` حُذفا. كانا جدولاً ثانياً
    # للانتقالات يناقض جدول الخدمات (الموديل يسمح Bounced→Under_Collection،
    # الخدمات لا)، وميتَين إنتاجياً: لا مستدعي لهما خارج اختبارهما، لأن الحالة
    # تتغير حصراً عبر `accounting.services.transfer_cheque` التي ترحّل القيد
    # وتكتب الحركة. المصدر الواحد الآن: `INCOMING_TRANSITIONS` /
    # `OUTGOING_TRANSITIONS` في `accounting/services.py`.

    def __str__(self):
        return f"Cheque {self.cheque_number} - {self.amount}"


class ChequeMovement(models.Model):
    """N8-T14: سجل حركة الشيك (إيداع، صرف، رفض، إرجاع، تسوية)."""
    # CHQ-2: ترحيل السند نفسه صار يكتب حركته بدل `.update()` الأخرس — فأهمّ
    # حدث في حياة الشيك (دخوله الدفاتر) لم يعد غائباً عن سجلّه. قيد هذه
    # الحركات هو **قيد السند** فتُربط به مباشرة:
    #   `receive` وارد ← Received · `issue` صادر ← Under_Collection ·
    #   `revert` عكسهما عند إلغاء الترحيل (بلا قيد — قيد السند حُذف).
    # `issue` و`revert` من إنتاج المستند وحده: خارج `STATUS_MAP` وخارج جدولَي
    # الانتقالات، فلا تُستدعيان من الـAPI.
    MOVEMENT_TYPES = [
        ('receive', 'استلام'),
        ('issue', 'تسليم شيك صادر'),
        ('revert', 'إلغاء ترحيل السند'),
        ('deposit', 'إيداع'),
        ('redeposit', 'إعادة إيداع'),
        ('withdraw', 'صرف'),
        ('collect', 'تحصيل'),
        ('endorse', 'تظهير'),
        ('bounce', 'رفض'),
        ('return_to_customer', 'إرجاع للعميل'),
        ('cancel', 'إلغاء'),
        ('settle', 'تسوية'),
    ]
    id = models.AutoField(primary_key=True, db_column='ChequeMovementID')
    cheque = models.ForeignKey(
        Cheque, on_delete=models.CASCADE, db_column='ChequeID',
        related_name='movements',
    )
    movement_type = models.CharField(max_length=30, choices=MOVEMENT_TYPES, db_column='MovementType')
    # CHQ-1: قيد الحركة مربوطاً بها — كان السجل يقول «ماذا ومتى» ولا يقول
    # «أي قيد»، فأهمّ حدث في حياة الشيك (دخوله الدفاتر) غير قابل للتتبّع.
    journal = models.ForeignKey(
        'JournalHeader', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='cheque_movements',
    )
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy_UserID',
    )

    class Meta:
        db_table = 'cheque_movements'
        managed = True
        verbose_name = 'Cheque Movement'
        verbose_name_plural = 'Cheque Movements'

    def __str__(self):
        return f"{self.movement_type} — Cheque #{self.cheque_id}"


class AccountingAuditLog(models.Model):
    ACTIONS = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('POST', 'Post'),
    ]

    id = models.AutoField(primary_key=True, db_column='LogID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, db_column='UserID')
    action = models.CharField(max_length=20, choices=ACTIONS, db_column='Action')
    model_name = models.CharField(max_length=100, db_column='ModelName')
    object_id = models.IntegerField(db_column='ObjectID')
    change_details = models.TextField(db_column='ChangeDetails')
    timestamp = models.DateTimeField(auto_now_add=True, db_column='Timestamp')

    class Meta:
        db_table = 'accounting_audit_logs'
        managed = True

class CashBoxLedgerAccount(models.Model):
    """صندوق نقدي — الكيان الأول للخزينة، وحسابُه في الشجرة وجهُه المحاسبي.

    T-CASHBOX M2: كان مجرّد «جسر ربط» لصندوق خارجي (مستند مرآة
    `cashBoxes/{id}`)، فصار هو الصندوق نفسه: يُنشأ خادمياً بمعاملة واحدة
    (`accounting/services.py` (`create_cash_box`)) تكتب الحساب والربط ووثيقة
    المرآة معاً. `external_id` يبقى مفتاح التوافق مع قرّاء المرآة القدامى
    ويولّده الخادم إن لم يُمرَّر.
    """

    id = models.AutoField(primary_key=True, db_column="CashBoxLedgerID")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column="TenantID")
    external_id = models.CharField(max_length=128, db_column="ExternalID")
    name = models.CharField(max_length=200, db_column="Name")
    currency_code = models.CharField(max_length=3, default="USD", db_column="CurrencyCode")
    account = models.OneToOneField(
        Account,
        on_delete=models.CASCADE,
        related_name="cash_box_ledger",
        db_column="AccountID",
    )
    #: صندوق الشركة الافتراضي. الوحدانية مفروضة في طبقة الخدمة داخل المعاملة
    #: (`set_default_cash_box`) لا بقيد شرطي: MySQL بلا فهارس جزئية، فقيدٌ
    #: بـ`condition=` يوجد في قاعدة الاختبارات (SQLite) ويغيب بصمت عن الإنتاج.
    is_default = models.BooleanField(default=False, db_column="IsDefault")
    is_active = models.BooleanField(default=True, db_column="IsActive")
    notes = models.TextField(null=True, blank=True, db_column="Notes")
    created_at = models.DateTimeField(
        auto_now_add=True, null=True, blank=True, db_column="CreatedAt")

    class Meta:
        db_table = "cash_box_ledger_accounts"
        managed = True
        unique_together = [["tenant", "external_id"]]

    def __str__(self):
        return f"{self.name} ({self.external_id})"


class CashBoxUserDefault(models.Model):
    """صندوق المستخدم الافتراضي داخل شركة — أعلى درجة في سلّم حلّ الصندوق.

    يسكن في `accounting` لا على عضوية `tenants`: `accounting` يستورد `tenants`
    أصلاً، فمفتاحٌ أجنبي في الاتجاه المعاكس دورةُ استيراد.
    """

    id = models.AutoField(primary_key=True, db_column="CashBoxUserDefaultID")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column="TenantID")
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, db_column="UserID",
        related_name="cash_box_defaults")
    cash_box = models.ForeignKey(
        CashBoxLedgerAccount, on_delete=models.CASCADE, db_column="CashBoxLedgerID",
        related_name="user_defaults")

    class Meta:
        db_table = "cash_box_user_defaults"
        managed = True
        unique_together = [["tenant", "user"]]

    def __str__(self):
        return f"{self.user_id} → {self.cash_box_id}"


class CashBoxFxLot(models.Model):
    """طبقة FIFO لصندوق بعملة أجنبية (مثل صندوق الدولار).

    كل إيداع/تحويل ينشئ طبقة بسعر صرفها وقت التمويل. عند الدفع بالعملة الأجنبية
    تُستهلَك الطبقات بترتيب FIFO (الأقدم أولاً)، والتكلفة بالعملة الأساسية تُحسب
    بسعر كل طبقة. رصيد حساب الصندوق في الشجرة = القيمة الدفترية بالشيقل
    (مجموع remaining_fc × rate).
    """

    SOURCE_CAPITAL = 'capital'
    SOURCE_TRANSFER = 'transfer_ils'
    SOURCE_CHOICES = [
        (SOURCE_CAPITAL, 'إيداع من رأس المال'),
        (SOURCE_TRANSFER, 'تحويل من صندوق الشيقل'),
    ]

    id = models.AutoField(primary_key=True, db_column='CashBoxFxLotID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    cash_box = models.ForeignKey(
        CashBoxLedgerAccount, on_delete=models.CASCADE,
        db_column='CashBoxLedgerID', related_name='fx_lots',
        help_text='صندوق العملة الأجنبية صاحب الطبقة')
    lot_date = models.DateField(db_column='LotDate')
    original_fc = models.DecimalField(max_digits=18, decimal_places=4, db_column='OriginalFC',
        help_text='المبلغ الأصلي بالعملة الأجنبية')
    remaining_fc = models.DecimalField(max_digits=18, decimal_places=4, db_column='RemainingFC',
        help_text='المتبقي بالعملة الأجنبية (يُستهلَك FIFO)')
    rate = models.DecimalField(max_digits=18, decimal_places=6, db_column='Rate',
        help_text='سعر صرف الطبقة: شيقل لكل وحدة عملة أجنبية')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_column='Source')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='fx_lots',
        help_text='قيد التمويل')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'cash_box_fx_lots'
        managed = True
        ordering = ['lot_date', 'id']  # ترتيب FIFO

    def __str__(self):
        return f"Lot {self.id}: {self.remaining_fc}/{self.original_fc} @ {self.rate}"


class CashTransfer(models.Model):
    """تحويل نقدي بين خزينتين — صندوق↔صندوق أو صندوق↔بنك.

    T-CASHBOX M6: مستندٌ بطرفين وقيدٌ واحد، بدل أن يكون التحويل «إيداعاً هنا
    وسحباً هناك» لا يربطهما شيء. الطرف الواحد إمّا صندوق أو حساب بنكي — يحرسه
    `create_cash_transfer` لا قيدٌ في القاعدة (طرفان اختياريان بطبيعتهما).
    """

    id = models.AutoField(primary_key=True, db_column='CashTransferID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    number = models.IntegerField(default=0, db_column='Number')
    transfer_date = models.DateField(db_column='TransferDate')
    from_cash_box = models.ForeignKey(
        CashBoxLedgerAccount, on_delete=models.PROTECT, null=True, blank=True,
        db_column='FromCashBoxID', related_name='transfers_out')
    from_bank_account = models.ForeignKey(
        'BankAccount', on_delete=models.PROTECT, null=True, blank=True,
        db_column='FromBankAccountID', related_name='transfers_out')
    to_cash_box = models.ForeignKey(
        CashBoxLedgerAccount, on_delete=models.PROTECT, null=True, blank=True,
        db_column='ToCashBoxID', related_name='transfers_in')
    to_bank_account = models.ForeignKey(
        'BankAccount', on_delete=models.PROTECT, null=True, blank=True,
        db_column='ToBankAccountID', related_name='transfers_in')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount',
                                 help_text='المبلغ بعملة الطرف المُرسِل')
    rate = models.DecimalField(max_digits=18, decimal_places=6, default=1,
                               db_column='Rate', help_text='سعر الصرف حين تختلف العملتان')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='cash_transfers')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy', related_name='cash_transfers')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'cash_transfers'
        managed = True
        ordering = ['-transfer_date', '-id']

    def __str__(self):
        return f"تحويل #{self.number or self.id}: {self.amount}"


class CashCount(models.Model):
    """جرد صندوق — عدّ النقد الفعلي ومقارنته بالرصيد الدفتري.

    T-CASHBOX M6: الفرق (عجز/زيادة) يُرحَّل قيداً إلى حسابَي العجز والزيادة
    المعرَّفين في الإعدادات — نمط Odoo (Profit/Loss Account). `denominations`
    تفصيل عدّ الفئات كما أدخله العادّ، محفوظ للمراجعة لا للحساب: الإجمالي
    المعتمد هو `counted_total`.
    """

    STATUS_DRAFT = 'draft'
    STATUS_POSTED = 'posted'
    STATUS_CHOICES = [(STATUS_DRAFT, 'مسودة'), (STATUS_POSTED, 'مرحَّل')]

    id = models.AutoField(primary_key=True, db_column='CashCountID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    cash_box = models.ForeignKey(
        CashBoxLedgerAccount, on_delete=models.PROTECT,
        db_column='CashBoxLedgerID', related_name='counts')
    count_date = models.DateField(db_column='CountDate')
    book_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0,
                                       db_column='BookBalance',
                                       help_text='الرصيد الدفتري لحظة الجرد')
    counted_total = models.DecimalField(max_digits=18, decimal_places=2, default=0,
                                        db_column='CountedTotal')
    difference = models.DecimalField(max_digits=18, decimal_places=2, default=0,
                                     db_column='Difference',
                                     help_text='المعدود − الدفتري: موجب زيادة، سالب عجز')
    denominations = models.JSONField(null=True, blank=True, db_column='Denominations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_DRAFT, db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='cash_counts')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy', related_name='cash_counts')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'cash_counts'
        managed = True
        ordering = ['-count_date', '-id']

    def __str__(self):
        return f"جرد {self.cash_box_id} @ {self.count_date}: {self.difference}"


#: issue #80 — عاديّ/مرتجع على سندَي المصروف والإيراد معاً: يقلب اتجاه القيد
#: (مدين↔دائن) ويُبقي المبلغ موجباً، مرآة `SalesInvoice.INVOICE_KIND_CHOICES`
#: (بيع/مرجع بيع). ثابتٌ واحد يُشارَك بين الموديلين بدل تكرار نفس السلسلتين.
VOUCHER_KIND_NORMAL = 'normal'
VOUCHER_KIND_RETURN = 'return'
VOUCHER_KIND_CHOICES = [
    (VOUCHER_KIND_NORMAL, 'عاديّ'),
    (VOUCHER_KIND_RETURN, 'مرتجع'),
]


class ExpenseVoucher(models.Model):
    """سند مصروف — مستندٌ عامٌّ لكل شركة، بلا مورّدٍ إلزامي وبلا مخزون (issue #56).

    يسدّ الفجوة بين فاتورة الشراء (تلزمها 1104 مخزون) وسند الصرف
    (`sales.SupplierPayment`، مورّده إلزامي بـ`PROTECT`): مصروفٌ عاديّ —
    كهرباء، إيجار، بنزين — لا مورّد له ولا بضاعة. المستفيد اختياري عمداً:
    شريكٌ إن وُجد، أو اسمٌ نصّي، أو لا شيء.
    """

    PAYMENT_CASH = 'cash'
    PAYMENT_CHEQUE = 'cheque'
    PAYMENT_ON_ACCOUNT = 'on_account'
    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_CASH, 'صندوق/بنك'),
        (PAYMENT_CHEQUE, 'شيك'),
        (PAYMENT_ON_ACCOUNT, 'على الحساب'),
    ]

    KIND_NORMAL = VOUCHER_KIND_NORMAL
    KIND_RETURN = VOUCHER_KIND_RETURN
    KIND_CHOICES = VOUCHER_KIND_CHOICES

    id = models.AutoField(primary_key=True, db_column='ExpenseVoucherID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    number = models.IntegerField(default=0, db_column='Number')
    date = models.DateField(db_column='Date')
    expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        db_column='ExpenseAccountID', related_name='expense_vouchers')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount')
    tax_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column='TaxAmount',
        help_text='ضريبة مدخلات (1105) — جزء من amount لا إضافة عليه')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID')
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=1, db_column='ExchangeRate')
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_CASH, db_column='PaymentMethod')
    kind = models.CharField(
        max_length=10, choices=KIND_CHOICES, default=KIND_NORMAL, db_column='Kind',
        help_text='عاديّ أو مرتجع — يقلب اتجاه القيد ويُبقي المبلغ موجباً (issue #80).')
    cash_or_bank_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        db_column='CashAccountID', related_name='expense_vouchers_cash',
        help_text='الصندوق/البنك — يُملأ فقط عند payment_method=cash')
    beneficiary_partner = models.ForeignKey(
        Partner, on_delete=models.PROTECT, null=True, blank=True,
        db_column='BeneficiaryPartnerID', related_name='expense_vouchers')
    beneficiary_name = models.CharField(max_length=200, blank=True, default='', db_column='BeneficiaryName')
    description = models.CharField(max_length=500, blank=True, default='', db_column='Description')
    attachment_url = models.URLField(blank=True, default='', max_length=500, db_column='AttachmentUrl')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='expense_vouchers')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy', related_name='expense_vouchers')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'expense_vouchers'
        managed = True
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['tenant', '-date', '-id'], name='idx_expvouch_tenant_date'),
        ]

    def __str__(self):
        return f"سند مصروف #{self.number or self.id}: {self.amount}"


class RevenueVoucher(models.Model):
    """سند إيراد — مرآة حرفية لـ`ExpenseVoucher` بعكس الاتجاه (issue #80).

    يسدّ الفجوة نفسها من جهة الإيراد: عمولة، خدمة عارضة، إيجارٌ نحصّله — إيرادٌ
    لا فاتورة بيع له ولا بضاعة. الدافع اختياري عمداً: شريكٌ إن وُجد، أو اسمٌ
    نصّي، أو لا شيء. **لا يُنشئ منتجاً خدمياً ولا يفرّغ `SalesInvoiceLine.product`**
    — مرفوضان صراحةً في المواصفة (#77 القسم ٢).
    """

    PAYMENT_CASH = 'cash'
    PAYMENT_CHEQUE = 'cheque'
    PAYMENT_ON_ACCOUNT = 'on_account'
    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_CASH, 'صندوق/بنك'),
        (PAYMENT_CHEQUE, 'شيك'),
        (PAYMENT_ON_ACCOUNT, 'على الحساب'),
    ]

    KIND_NORMAL = VOUCHER_KIND_NORMAL
    KIND_RETURN = VOUCHER_KIND_RETURN
    KIND_CHOICES = VOUCHER_KIND_CHOICES

    id = models.AutoField(primary_key=True, db_column='RevenueVoucherID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    number = models.IntegerField(default=0, db_column='Number')
    date = models.DateField(db_column='Date')
    revenue_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        db_column='RevenueAccountID', related_name='revenue_vouchers')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount')
    tax_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column='TaxAmount',
        help_text='ضريبة مخرجات (2104) — جزء من amount لا إضافة عليه')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID')
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=1, db_column='ExchangeRate')
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_CASH, db_column='PaymentMethod')
    kind = models.CharField(
        max_length=10, choices=KIND_CHOICES, default=KIND_NORMAL, db_column='Kind',
        help_text='عاديّ أو مرتجع — يقلب اتجاه القيد ويُبقي المبلغ موجباً (issue #80).')
    cash_or_bank_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        db_column='CashAccountID', related_name='revenue_vouchers_cash',
        help_text='الصندوق/البنك — يُملأ فقط عند payment_method=cash')
    payer_partner = models.ForeignKey(
        Partner, on_delete=models.PROTECT, null=True, blank=True,
        db_column='PayerPartnerID', related_name='revenue_vouchers')
    payer_name = models.CharField(max_length=200, blank=True, default='', db_column='PayerName')
    description = models.CharField(max_length=500, blank=True, default='', db_column='Description')
    attachment_url = models.URLField(blank=True, default='', max_length=500, db_column='AttachmentUrl')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='revenue_vouchers')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy', related_name='revenue_vouchers')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'revenue_vouchers'
        managed = True
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['tenant', '-date', '-id'], name='idx_revvouch_tenant_date'),
        ]

    def __str__(self):
        return f"سند إيراد #{self.number or self.id}: {self.amount}"


class Bank(models.Model):
    """T-BANKS: بنك تتعامل معه الشركة — مظلّة لفروعه وحساباته.

    البنك نفسه بلا حساب في الشجرة؛ الحسابات البنكية (BankAccount) هي ما يُربط
    بحساب أستاذ تحت «1102 البنوك».
    """

    id = models.AutoField(primary_key=True, db_column='BankID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    name = models.CharField(max_length=150, db_column='Name')
    code = models.CharField(max_length=30, null=True, blank=True, db_column='Code',
                            help_text='رمز البنك المحلي (اختياري)')
    swift_code = models.CharField(max_length=20, null=True, blank=True, db_column='SwiftCode')
    country = models.CharField(max_length=80, null=True, blank=True, db_column='Country')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    is_active = models.BooleanField(default=True, db_column='IsActive')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'banks'
        managed = True
        unique_together = [['tenant', 'name']]
        ordering = ['name']

    def __str__(self):
        return self.name


class BankBranch(models.Model):
    """فرع بنك — عنوان الفرع الذي يُفتح فيه الحساب أو يُسحب عليه الشيك."""

    id = models.AutoField(primary_key=True, db_column='BankBranchID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, db_column='BankID',
                             related_name='branches')
    name = models.CharField(max_length=150, db_column='Name')
    branch_code = models.CharField(max_length=30, null=True, blank=True, db_column='BranchCode')
    address = models.CharField(max_length=255, null=True, blank=True, db_column='Address')
    phone = models.CharField(max_length=50, null=True, blank=True, db_column='Phone')
    is_active = models.BooleanField(default=True, db_column='IsActive')

    class Meta:
        db_table = 'bank_branches'
        managed = True
        unique_together = [['bank', 'name']]
        ordering = ['name']

    def __str__(self):
        return f"{self.bank.name} — {self.name}"


class BankAccount(models.Model):
    """حساب الشركة لدى بنك — بعملته وحسابه في شجرة الحسابات.

    الحساب في الشجرة (`account`) يُنشأ تلقائياً تحت «1102 البنوك» عند إنشاء
    الحساب البنكي، فكل حركة بنكية تُرحَّل على حسابها الخاص لا على حساب عام.
    """

    id = models.AutoField(primary_key=True, db_column='BankAccountID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, db_column='BankID',
                             related_name='accounts')
    branch = models.ForeignKey(BankBranch, on_delete=models.SET_NULL, null=True, blank=True,
                               db_column='BankBranchID', related_name='accounts')
    name = models.CharField(max_length=150, db_column='Name',
                            help_text='تسمية الحساب كما تظهر في الشجرة والتقارير')
    account_number = models.CharField(max_length=50, null=True, blank=True, db_column='AccountNumber')
    iban = models.CharField(max_length=50, null=True, blank=True, db_column='IBAN')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID',
                                 related_name='bank_accounts')
    account = models.OneToOneField(Account, on_delete=models.PROTECT, db_column='AccountID',
                                   related_name='bank_account')
    is_default = models.BooleanField(default=False, db_column='IsDefault')
    is_active = models.BooleanField(default=True, db_column='IsActive')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        # `bank_accounts` محجوز لجدول legacy فارغ من السكيما الأصلية (بلا موديل
        # ولا مستهلك) — لا نلمسه، فاسم جدولنا مستقل.
        db_table = 'company_bank_accounts'
        managed = True
        ordering = ['bank__name', 'name']

    def __str__(self):
        return f"{self.bank.name} — {self.name} ({self.currency.Code})"


class BankReconciliation(models.Model):
    """مطابقة بنكية: كشف البنك مقابل الدفاتر حتى تاريخ معيّن.

    الأسطر المؤشَّرة (BankReconciliationLine) هي حركات الدفاتر التي ظهرت في
    كشف البنك. الفرق = رصيد الكشف − (رصيد الدفاتر المؤشَّر). لا تُغلق المطابقة
    إلا بفرق صفر — كما في البرامج المهنية.
    """

    STATUS_OPEN = 'Open'
    STATUS_CLOSED = 'Closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'مفتوحة'),
        (STATUS_CLOSED, 'مُقفلة'),
    ]

    id = models.AutoField(primary_key=True, db_column='BankReconciliationID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE,
                                     db_column='BankAccountID', related_name='reconciliations')
    statement_date = models.DateField(db_column='StatementDate')
    statement_balance = models.DecimalField(max_digits=18, decimal_places=2,
                                            db_column='StatementBalance', default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN,
                              db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   db_column='CreatedBy_UserID')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    closed_at = models.DateTimeField(null=True, blank=True, db_column='ClosedAt')

    class Meta:
        db_table = 'bank_reconciliations'
        managed = True
        ordering = ['-statement_date', '-id']

    def __str__(self):
        return f"مطابقة {self.bank_account_id} حتى {self.statement_date}"


class BankReconciliationLine(models.Model):
    """سطر دفاتر مؤشَّر أنه ظهر في كشف البنك.

    `journal_line` فريد عالمياً: الحركة تُطابَق مرة واحدة فقط.
    """

    id = models.AutoField(primary_key=True, db_column='BankReconciliationLineID')
    reconciliation = models.ForeignKey(BankReconciliation, on_delete=models.CASCADE,
                                       db_column='BankReconciliationID', related_name='lines')
    journal_line = models.OneToOneField(JournalLine, on_delete=models.CASCADE,
                                        db_column='JLineID', related_name='bank_reconciliation_line')
    cleared_at = models.DateTimeField(auto_now_add=True, db_column='ClearedAt')

    class Meta:
        db_table = 'bank_reconciliation_lines'
        managed = True

    def __str__(self):
        return f"سطر {self.journal_line_id} ← مطابقة {self.reconciliation_id}"


class FiscalPeriod(models.Model):
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    ]

    id = models.AutoField(primary_key=True, db_column='PeriodID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    name = models.CharField(max_length=100, db_column='PeriodName')
    start_date = models.DateField(db_column='StartDate')
    end_date = models.DateField(db_column='EndDate')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open', db_column='Status')
    is_closed = models.BooleanField(default=False, db_column='IsClosed')

    class Meta:
        db_table = 'fiscal_periods'
        managed = True

    def __str__(self):
        return f"{self.name} ({self.status})"


class ExchangeRate(models.Model):
    id = models.AutoField(primary_key=True, db_column='ExchangeRateID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    from_currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, related_name='rates_from',
        db_column='FromCurrencyID',
    )
    to_currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, related_name='rates_to',
        db_column='ToCurrencyID',
    )
    rate = models.DecimalField(max_digits=18, decimal_places=6, db_column='Rate')
    effective_date = models.DateField(db_column='EffectiveDate')

    class Meta:
        db_table = 'exchange_rates'
        managed = True
        unique_together = [['tenant', 'from_currency', 'to_currency', 'effective_date']]

    def __str__(self):
        return f"{self.from_currency} -> {self.to_currency} @ {self.rate} ({self.effective_date})"


class TaxRate(models.Model):
    """نسبة ضريبية (VAT). اتجاه الضريبة يُحدّد الحساب المناسب:
    - sales  → يُستخدم مع فواتير المبيعات (ضريبة مخرجات Output VAT — خصم)
    - purchase → يُستخدم مع فواتير الشراء (ضريبة مدخلات Input VAT — أصل)
    - both   → يُستخدم للطرفين (غير مُستحسن محاسبياً لأن الحسابَين مختلفان)
    """

    DIRECTION_CHOICES = [
        ('sales', 'Sales / Output'),
        ('purchase', 'Purchase / Input'),
        ('both', 'Both'),
    ]

    id = models.AutoField(primary_key=True, db_column='TaxRateID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    name = models.CharField(max_length=100, db_column='Name')
    code = models.CharField(max_length=20, db_column='Code')
    rate = models.DecimalField(max_digits=5, decimal_places=2, db_column='Rate')
    tax_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, db_column='TaxAccountID',
        related_name='tax_rates',
    )
    direction = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, default='both',
        db_column='Direction',
        help_text='اتجاه الضريبة: sales (مخرجات) / purchase (مدخلات) / both',
    )
    is_active = models.BooleanField(default=True, db_column='IsActive')

    class Meta:
        db_table = 'tax_rates'
        managed = True
        unique_together = [['tenant', 'code']]

    def __str__(self):
        return f"{self.name} ({self.rate}%) [{self.direction}]"


class OpeningBalance(models.Model):
    """مستند الأرصدة الافتتاحية للشركة — أرصدة الحسابات وبضاعة أول المدة معاً.

    مستندٌ واحد لكل شركة (لا لكل سنة): السنوات اللاحقة يخدمها `year_end_close`.
    ترحيله يُنتج **قيداً موحّداً واحداً** بمرجع `OPENING_BALANCE` مقابل حساب
    الموازنة `3300` (نفس حساب أرصدة الأطراف الافتتاحية، فتتجمّع كل أرجل الافتتاح
    في دلو حقوق ملكية واحد)، ويسجّل بضاعة أول المدة حركاتِ مخزون بنفس المرجع.
    أرصدة الأطراف تبقى على آليتها القائمة (`PARTNER_OPENING`، قيد لكل طرف) فلا
    يزدوج حساب الذمم — ولذلك يرفض `accounting/opening_balance.py` أي حساب ذمم أو
    مخزون في بنود الحسابات.

    `entry_date` مخزَّن ومشتقّ = `start_date − 1` (نمط Xero/Odoo): أرصدة الافتتاح
    هي أرصدة الإقفال في اليوم السابق لبدء التشغيل. حارس الفترة المالية يبقى
    مفروضاً عليه عبر `post_journal` — لا انزلاق صامت للتاريخ.

    «قيد افتتاحي مرحّل واحد لكل شركة» مفروضٌ في `post_opening_balance` داخل
    المعاملة تحت `select_for_update`، لا بقيد فريد شرطي: MySQL لا يدعم الفهارس
    الجزئية (`supports_partial_indexes = False`) فكان القيد سيوجد في قاعدة
    الاختبارات (SQLite) ويغيب بصمت عن الإنتاج.
    """

    STATUS_DRAFT = 'draft'
    STATUS_POSTED = 'posted'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'مسودة'),
        (STATUS_POSTED, 'مرحّل'),
    ]

    id = models.AutoField(primary_key=True, db_column='OpeningBalanceID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID',
        related_name='opening_balances',
    )
    start_date = models.DateField(
        null=True, blank=True, db_column='StartDate',
        help_text='تاريخ بدء التشغيل على النظام — أول يوم عمل فعلي',
    )
    entry_date = models.DateField(
        null=True, blank=True, db_column='EntryDate',
        help_text='تاريخ القيد الافتتاحي = تاريخ البدء ناقص يوماً (يُشتقّ تلقائياً)',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT,
        db_column='Status',
    )
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='opening_balances',
    )
    posted_at = models.DateTimeField(null=True, blank=True, db_column='PostedAt')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy_UserID', related_name='opening_balances',
    )

    class Meta:
        db_table = 'opening_balances'
        managed = True
        ordering = ['-id']

    def __str__(self):
        return f"أرصدة افتتاحية {self.entry_date or '—'} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """يشتقّ `entry_date` من `start_date` — نقطة واحدة تضمن العلاقة من كل مسار."""
        if self.start_date:
            self.entry_date = self.start_date - datetime.timedelta(days=1)
        else:
            self.entry_date = None
        super().save(*args, **kwargs)


class OpeningBalanceAccountLine(models.Model):
    """رصيد افتتاحي لحساب واحد — طرف واحد فقط (مدين أو دائن)."""

    id = models.AutoField(primary_key=True, db_column='OpeningBalanceLineID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    opening = models.ForeignKey(
        OpeningBalance, on_delete=models.CASCADE, db_column='OpeningBalanceID',
        related_name='account_lines',
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, db_column='AccountID',
        related_name='opening_balance_lines',
    )
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='Debit')
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='Credit')
    notes = models.CharField(max_length=500, blank=True, default='', db_column='Notes')

    class Meta:
        db_table = 'opening_balance_account_lines'
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=['opening', 'account'],
                name='uniq_opening_account',
            ),
            models.CheckConstraint(
                condition=models.Q(debit__gte=0),
                name='opening_account_debit_non_negative',
            ),
            models.CheckConstraint(
                condition=models.Q(credit__gte=0),
                name='opening_account_credit_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.account}: {self.debit} / {self.credit}"


class OpeningBalanceStockLine(models.Model):
    """بضاعة أول المدة: كمية منتج في مستودع بتكلفة وحدتها.

    المستودع إلزامي — جردٌ افتتاحي بلا موقع لا معنى له، والقيد الفريد
    `(opening, product, warehouse)` لا يعمل على عمود يقبل NULL في MySQL.
    """

    id = models.AutoField(primary_key=True, db_column='OpeningBalanceStockLineID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    opening = models.ForeignKey(
        OpeningBalance, on_delete=models.CASCADE, db_column='OpeningBalanceID',
        related_name='stock_lines',
    )
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.PROTECT, db_column='ProductID',
        related_name='opening_balance_lines',
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT, db_column='WarehouseID',
        related_name='opening_balance_lines',
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column='Quantity')
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, db_column='UnitCost')

    class Meta:
        db_table = 'opening_balance_stock_lines'
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=['opening', 'product', 'warehouse'],
                name='uniq_opening_product_warehouse',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='opening_stock_quantity_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(unit_cost__gte=0),
                name='opening_stock_unit_cost_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.product}: {self.quantity} × {self.unit_cost}"
