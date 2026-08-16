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
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Under_Collection', 'Under Collection'),
        ('Collected', 'Collected'),
        ('Bounced', 'Bounced'),
        ('Returned', 'Returned'),
        ('Settled', 'Settled'),
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

    VALID_TRANSITIONS = {
        'Draft': ['Under_Collection', 'Bounced', 'Returned'],
        'Under_Collection': ['Collected', 'Bounced', 'Returned'],
        'Collected': ['Bounced', 'Returned'],
        'Bounced': ['Draft', 'Under_Collection', 'Returned'],
        'Returned': [],
    }

    def save(self, *args, **kwargs):
        """T-BANKS: لقطة اسم البنك/الفرع من السجل المرتبط للعرض التاريخي."""
        if self.bank_id and not (self.bank_name or '').strip():
            self.bank_name = (self.bank.name or '')[:100]
        if self.bank_branch_ref_id and not (self.bank_branch or '').strip():
            self.bank_branch = (self.bank_branch_ref.name or '')[:100]
        super().save(*args, **kwargs)

    def change_status(self, new_status, *, notes='', user=None):
        """P-H-4: تغيير حالة الشيك مع تسجيل الحركة والتحقق من الانتقال الصحيح.

        Returns: ChequeMovement that was created.
        Raises: ValidationError if transition is invalid.
        """
        from django.core.exceptions import ValidationError

        if new_status == self.status:
            return None
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"لا يمكن تغيير حالة الشيك من {self.status} إلى {new_status}. "
                f"الانتقالات المسموحة من {self.status}: {', '.join(allowed) if allowed else '—'}."
            )
        self.status = new_status
        self.save(update_fields=['status'])
        from django.utils import timezone
        movement_type_map = {
            'Under_Collection': 'deposit',
            'Collected': 'settle',
            'Bounced': 'bounce',
            'Returned': 'return_to_customer',
        }
        movement_type = movement_type_map.get(new_status, new_status.lower())
        return ChequeMovement.objects.create(
            cheque=self,
            movement_type=movement_type,
            notes=notes or '',
            created_by=user if user and not getattr(user, 'is_anonymous', False) else None,
        )

    def __str__(self):
        return f"Cheque {self.cheque_number} - {self.amount}"


class ChequeMovement(models.Model):
    """N8-T14: سجل حركة الشيك (إيداع، صرف، رفض، إرجاع، تسوية)."""
    MOVEMENT_TYPES = [
        ('deposit', 'إيداع'),
        ('withdraw', 'صرف'),
        # T-CHQ2: `transfer_cheque` تكتب 'collect' منذ task11 وهي ليست ضمن
        # الخيارات، فيعرضها `get_movement_type_display` خاماً بالإنجليزية.
        ('collect', 'تحصيل'),
        ('bounce', 'رفض'),
        ('return_to_customer', 'إرجاع للعميل'),
        ('settle', 'تسوية'),
    ]
    id = models.AutoField(primary_key=True, db_column='ChequeMovementID')
    cheque = models.ForeignKey(
        Cheque, on_delete=models.CASCADE, db_column='ChequeID',
        related_name='movements',
    )
    movement_type = models.CharField(max_length=30, choices=MOVEMENT_TYPES, db_column='MovementType')
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
    """
    يربط صندوقاً خارجياً (مثل مستند Firestore cashBoxes/{id}) بحساب أصل (صندوق/نقدية) في الشجرة.
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

    class Meta:
        db_table = "cash_box_ledger_accounts"
        managed = True
        unique_together = [["tenant", "external_id"]]

    def __str__(self):
        return f"{self.name} ({self.external_id})"


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
