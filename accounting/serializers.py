from decimal import Decimal

from rest_framework import serializers
from .models import (
    Account, JournalHeader, JournalLine, Cheque, ChequeMovement, CostCenter,
    CashBoxLedgerAccount, CashCount, CashTransfer, ExchangeRate, ExpenseVoucher,
    RevenueVoucher, PartnerAccountCodingRule,
    FiscalPeriod, TaxRate,
    Bank, BankBranch, BankAccount, BankReconciliation,
    OpeningBalanceAccountLine, OpeningBalanceStockLine,
)
from inventory.models import Product, Warehouse
from partners.models import Partner
from core.api_defaults import TenantScopedPrimaryKeyRelatedField
from core.terminology import term as tenant_term

class AccountSerializer(serializers.ModelSerializer):
    """يُرجع معلومات المورد المرتبط بالحساب (الاسم التجاري / المستعار) إن وُجد."""

    linked_partner = serializers.SerializerMethodField()
    # THA-292: الأب مقيّد بشركة الطلب — الحقل المولَّد تلقائياً كان
    # `queryset=Account.objects.all()` فيقبل أباً من شركة أخرى وينشئ فرعاً
    # عابراً للشركات (`get_queryset` في الـviewset يحمي القراءة فقط).
    parent = TenantScopedPrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'parent', 'account_type', 'sub_type', 'is_active',
            'linked_partner',
        ]

    def get_linked_partner(self, obj):
        prefetched = getattr(obj, '_api_linked_partners', None)
        if prefetched is not None:
            p = prefetched[0] if prefetched else None
        else:
            # توافق مع استخدام AccountSerializer منفرداً خارج AccountViewSet.
            p = Partner.objects.filter(
                tenant_id=obj.tenant_id, linked_account_id=obj.id,
            ).only('id', 'name', 'legal_name', 'partner_type').first()
        if not p:
            return None
        return {
            'id': p.id,
            'trade_name': p.name or '',
            'legal_name': p.legal_name or '',
            # T-COAMENU: النوع يقود إجراءات كبسة اليمين على الحساب — بدونه لا
            # تعرف الشجرة أتقترح فاتورة مبيعات وسند قبض أم فاتورة شراء وسند صرف.
            'partner_type': p.partner_type or '',
        }

class CostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCenter
        fields = '__all__'

class JournalLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    # Use PrimaryKeyRelatedField for strict ID validation
    # P1-8: مقيّدان بشركة الطلب — سطر القيد اليدوي كان يقبل شريكاً/مركز
    # كلفة من أي شركة (post_journal لا يتحقق من ذلك — SCALABILITY_AUDIT §4).
    partner = TenantScopedPrimaryKeyRelatedField(
        queryset=Partner.objects.all(),
        many=False,
        read_only=False,
        required=False,
        allow_null=True
    )
    cost_center = TenantScopedPrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(),
        many=False,
        read_only=False,
        required=False,
        allow_null=True
    )

    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'debit', 'credit', 'base_debit', 'base_credit', 'partner', 'cost_center', 'description', 'project_id']


def _resolve_logistics_payment(rid, pay_map=None):
    """إرجاع كائن LogisticsPayment بعلاقاته أو None."""
    pay_map = pay_map or {}
    p = pay_map.get(rid)
    if not p:
        try:
            from logistics.models import LogisticsPayment
            p = (
                LogisticsPayment.objects
                .select_related("deal", "deal__partner")
                .filter(pk=rid)
                .first()
            )
        except Exception:
            p = None
    return p


def build_journal_reference_summary(obj, pay_map=None, sales_map=None, cust_map=None):
    """ملخص مرجع القيد: رقم الصفقة + اسم المصنع + المورد + رقم الدفعة.

    perf: sales_map/cust_map (اختياريان) يُمرّران من قائمة القيود لتفادي N+1 —
    استعلام لكل صف SALES_INVOICE/CUSTOMER_PAYMENT. عند غيابهما يسقط لاستعلام مفرد
    (للاستهلاك المفرد للـserializer خارج القائمة). نفس نمط pay_map."""
    rt = (obj.reference_type or "").strip()
    rid = obj.reference_id

    if rt == "LOGISTICS_PAYMENT" and rid:
        p = _resolve_logistics_payment(rid, pay_map)
        if p and getattr(p, "deal", None):
            d = p.deal
            ref = d.ref_number or f"#{d.pk}"
            # وصف الصفقة هو الأولوية القصوى (الحقل original_offer_number)
            deal_desc = (d.original_offer_number or "").strip()
            partner_obj = getattr(d, "partner", None)
            trade_name = (getattr(partner_obj, "name", "") or "").strip()
            # اسم المورد للمرجعية
            supplier_name = (d.factory_name or "").strip() or trade_name
            # البيان: وصف الصفقة أولاً، ثم اسم المورد للمرجع
            name_parts = []
            if deal_desc:
                name_parts.append(deal_desc)
            if supplier_name and supplier_name != deal_desc:
                name_parts.append(f"({supplier_name})")
            name_str = " ".join(name_parts)
            deal_part = f"صفقة {ref}" + (f" — {name_str}" if name_str else "")
            payment_part = f"دفعة {p.payment_number}"
            return f"{deal_part} · {payment_part}"

    if rt == "PURCHASE_RECEIPT":
        return f"استلام مخزون · مرجع {rid or '—'}"

    if rt == "JOURNAL_REVERSAL":
        return f"عكس قيد #{rid}"

    if rt == "LOGISTICS_EXPENSE":
        return f"مصروف لوجستي · مرجع {rid or '—'}"

    if rt == "LOGISTICS_CLEARANCE_PAYMENT" and rid:
        try:
            from logistics.models import LogisticsClearance
            c = (
                LogisticsClearance.objects
                .select_related("shipment", "customs_broker")
                .filter(pk=rid)
                .first()
            )
            if c:
                ship_num = getattr(getattr(c, "shipment", None), "shipment_number", None) or f"#{rid}"
                broker_name = getattr(getattr(c, "customs_broker", None), "name", None) or "—"
                return f"دفع تخليص جمركي · شحنة {ship_num} · {broker_name}"
        except Exception:
            pass
        return f"دفع تخليص جمركي · #{rid}"

    if rt == "LOGISTICS_SHIPMENT":
        return f"تكلفة شحن · شحنة #{rid or '—'}"

    if rt == "SALES_INVOICE" and rid:
        try:
            inv = (sales_map or {}).get(rid)
            if inv is None and not sales_map:
                from sales.models import SalesInvoice
                inv = SalesInvoice.objects.select_related("customer").filter(pk=rid).first()
            if inv:
                cust = getattr(inv.customer, "name", "") or ""
                inv_label = tenant_term(obj.tenant, "doc.sales_invoice")
                return f"{inv_label} {inv.invoice_number}" + (f" — {cust}" if cust else "")
        except Exception:
            pass
        return f"{tenant_term(obj.tenant, 'doc.sales_invoice')} · #{rid}"

    if rt == "SALES_DELIVERY_COGS" and rid:
        return f"تكلفة بضاعة مباعة عند التسليم · فاتورة #{rid}"

    if rt == "CUSTOMER_PAYMENT" and rid:
        try:
            pay = (cust_map or {}).get(rid)
            if pay is None and not cust_map:
                from sales.models import CustomerPayment
                pay = CustomerPayment.objects.select_related("partner").filter(pk=rid).first()
            if pay:
                name = getattr(pay.partner, "name", "") or ""
                return f"تحصيل عميل · دفعة #{pay.pk}" + (f" — {name}" if name else "")
        except Exception:
            pass
        return f"تحصيل عميل · دفعة #{rid}"

    if rt == "PURCHASE_INVOICE" and rid:
        return f"فاتورة شراء · #{rid}"

    if rt and rid:
        return f"{rt} · #{rid}"
    return ""


def get_deal_ref_number(obj, pay_map=None):
    """استخراج رقم مرجع الصفقة (ref_number) من القيد للتنقل الفرونت."""
    rt = (obj.reference_type or "").strip()
    rid = obj.reference_id
    if rt == "LOGISTICS_PAYMENT" and rid:
        p = _resolve_logistics_payment(rid, pay_map)
        if p and getattr(p, "deal", None):
            return p.deal.ref_number or None
    return None


SOURCE_LABEL_MAP = {
    # ISSUE #82: "SALES_INVOICE" مقصودةٌ غائبة من هنا — اسمها يأتي من المعجم
    # (`core.terminology.term`) لأنه يتبدّل بقالب الشركة (اسمه البديل في مكتب
    # المحاسبة)، لا من قاموسٍ ثابت لكل الشركات.
    "SALES_DELIVERY_COGS": "تكلفة بضاعة مباعة",
    "CUSTOMER_PAYMENT": "تحصيل عميل",
    "PURCHASE_INVOICE": "فاتورة شراء",
    "PURCHASE_RECEIPT": "استلام مخزون",
    "LOGISTICS_PAYMENT": "دفعة لوجستية",
    "LOGISTICS_EXPENSE": "مصروف لوجستي",
    "LOGISTICS_SHIPMENT": "شحنة دولية",
    "LOGISTICS_CLEARANCE_PAYMENT": "دفعة تخليص",
    "JOURNAL_REVERSAL": "عكس قيد",
    "MANUAL": "قيد يدوي",
    # A3: قيد يدوي وسمه المحاسب «تسوية» — يُصفّى وحده في دفتر اليومية.
    "ADJUSTMENT": "قيد تسوية",
    "OPENING_BALANCE": "قيد افتتاحي",
}


def _get_source_label(rt: str, tenant=None) -> str:
    key = (rt or "").strip()
    if key == "SALES_INVOICE":
        return tenant_term(tenant, "doc.sales_invoice")
    return SOURCE_LABEL_MAP.get(key, rt or "")


def _get_tenant_name(obj) -> str:
    try:
        return (obj.tenant.CompanyName or "").strip()
    except Exception:
        return ""


class JournalHeaderListSerializer(serializers.ModelSerializer):
    """قائمة خفيفة بلا أسطر تفصيلية."""

    reference_summary = serializers.SerializerMethodField(read_only=True)
    deal_ref_number = serializers.SerializerMethodField(read_only=True)
    currency_code = serializers.SerializerMethodField(read_only=True)
    tenant_name = serializers.SerializerMethodField(read_only=True)
    source_label = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = JournalHeader
        fields = [
            "id",
            "transaction_date",
            "reference_type",
            "reference_id",
            "reference_summary",
            "deal_ref_number",
            "description",
            "is_posted",
            "currency",
            "exchange_rate",
            "currency_code",
            "tenant_name",
            "source_label",
            "created_by",
            "created_by_name",
        ]

    def get_currency_code(self, obj):
        return obj.currency.Code if obj.currency_id else None

    def get_created_by_name(self, obj):
        """A3: عمود «المستخدم» في دفتر اليومية. القيود القديمة بلا مستخدم → None
        (الواجهة تعرض «—»)."""
        if not obj.created_by_id:
            return None
        u = obj.created_by
        return f"{u.first_name} {u.last_name}".strip() or u.get_username()

    def get_reference_summary(self, obj):
        return build_journal_reference_summary(
            obj,
            self.context.get("logistics_payments"),
            sales_map=self.context.get("sales_invoices"),
            cust_map=self.context.get("customer_payments"),
        )

    def get_deal_ref_number(self, obj):
        return get_deal_ref_number(obj, self.context.get("logistics_payments"))

    def get_tenant_name(self, obj):
        return _get_tenant_name(obj)

    def get_source_label(self, obj):
        return _get_source_label(obj.reference_type, obj.tenant)


class JournalHeaderSerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)
    reference_summary = serializers.SerializerMethodField(read_only=True)
    deal_ref_number = serializers.SerializerMethodField(read_only=True)
    currency_code = serializers.SerializerMethodField(read_only=True)
    tenant_name = serializers.SerializerMethodField(read_only=True)
    source_label = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = JournalHeader
        fields = [
            'id',
            'transaction_date',
            'reference_type',
            'reference_id',
            'reference_summary',
            'deal_ref_number',
            'description',
            'is_posted',
            'currency',
            'exchange_rate',
            'currency_code',
            'tenant_name',
            'source_label',
            'lines',
        ]

    def get_currency_code(self, obj):
        return obj.currency.Code if obj.currency_id else None

    def get_reference_summary(self, obj):
        return build_journal_reference_summary(
            obj,
            self.context.get("logistics_payments"),
            sales_map=self.context.get("sales_invoices"),
            cust_map=self.context.get("customer_payments"),
        )

    def get_deal_ref_number(self, obj):
        return get_deal_ref_number(obj, self.context.get("logistics_payments"))

    def get_tenant_name(self, obj):
        return _get_tenant_name(obj)

    def get_source_label(self, obj):
        return _get_source_label(obj.reference_type, obj.tenant)

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        # Tenant might not be in validated_data if it's read_only in ViewSet
        # Reliance on journal.tenant is safer if ViewSet handles tenant assignment
        
        journal = JournalHeader.objects.create(**validated_data)
        
        for line_data in lines_data:
            line_data.pop('id', None)
            JournalLine.objects.create(
                journal=journal,
                tenant=journal.tenant, # ALWAYS use the journal's tenant
                **line_data
            )
        return journal

    def update(self, instance, validated_data):
        if instance.is_posted:
            raise serializers.ValidationError(
                {"non_field_errors": "لا يمكن تعديل قيد مرحّل. استخدم القيد العكسي بدلاً من ذلك."}
            )

        lines_data = validated_data.pop('lines', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if lines_data is not None:
            if not lines_data:
                raise serializers.ValidationError(
                    {"lines": "لا يمكن حفظ قيد بلا أسطر — يجب أن يحتوي القيد على سطر واحد على الأقل."}
                )
            existing_lines = {line.id: line for line in instance.lines.all()}
            seen_ids = set()

            for line_data in lines_data:
                line_id = line_data.get('id')
                if line_id and line_id in existing_lines:
                    line_instance = existing_lines[line_id]
                    for attr, value in line_data.items():
                        if attr != 'id':
                            setattr(line_instance, attr, value)
                    line_instance.save()
                    seen_ids.add(line_id)
                else:
                    line_data.pop('id', None)
                    JournalLine.objects.create(
                        journal=instance,
                        tenant=instance.tenant,
                        **line_data
                    )
            
            for line_id, line_instance in existing_lines.items():
                if line_id not in seen_ids:
                    line_instance.delete()

        return instance

class ChequeSerializer(serializers.ModelSerializer):
    # T-BANKS: أسماء البنك/الفرع/حساب الإيداع للعرض بلا استعلام إضافي في الواجهة.
    bank_display = serializers.SerializerMethodField(read_only=True)
    bank_branch_display = serializers.SerializerMethodField(read_only=True)
    deposit_bank_account_name = serializers.SerializerMethodField(read_only=True)
    # CHQ-3: الحالة بتسميتها الصحيحة حسب الاتجاه، والحركات المتاحة الآن —
    # من جدولَي الانتقالات في `accounting/services.py`. كانت الواجهة تحمل
    # نسختها من الجدول والتسميات، فتفترق النسختان بلا أن يشعر أحد.
    status_label = serializers.SerializerMethodField(read_only=True)
    allowed_movements = serializers.SerializerMethodField(read_only=True)
    # CHQ-4: المستند الذي دخل الشيك الدفاتر ضمنه، وهل ينتظر ترحيله. بدونهما
    # كانت ورقة السند المسودة طريقاً مسدوداً في الشاشة: حركاتٌ مرفوضة حتماً
    # ولا سبيل لمعرفة أي سند يُرحَّل ولا للوصول إليه.
    source_document = serializers.SerializerMethodField(read_only=True)
    needs_document_post = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Cheque
        fields = '__all__'
        # T-CHQ3: الشركة من الترويسة والمستخدم من التوكن — وبقاؤهما مطلوبَين
        # (FK بلا blank=True) كان يردّ كل إنشاء شيك من الشاشة بـ400.
        # CHQ-4: `endorsed_to` و`deposit_bank_account` قراءةٌ فقط — يكتبهما
        # `transfer_cheque` وحده مع قيد الحركة. كانا مفتوحَين لـPATCH خام،
        # فيتغيّر مستفيد التظهير بعد أن رُحِّل قيدٌ يدين ذممه ⇒ الصفّ يقول
        # طرفاً واليومية تقول آخر، بلا أي تعارض ظاهر يكشف ذلك.
        read_only_fields = [
            'tenant', 'created_by', 'created_at',
            'endorsed_to', 'deposit_bank_account',
        ]

    #: الحقائق المالية للورقة — يقرؤها قيدُ سندها. تغييرها بعد الترحيل يجعل
    #: القيد يصف ورقةً غير التي في الجدول.
    _LOCKED_AFTER_POSTING = ('amount', 'direction', 'partner', 'currency')

    def validate(self, attrs):
        """T-CHQ3: البنك المسحوب عليه أهمّ ما في الورقة — مسجَّلاً أو نصاً.

        على التعديل لا يُطبَّق الشرط إلا إذا مسّ الطلب حقول البنك، كي لا يمنع
        تحرير شيكات قديمة سُجِّلت بلا بنك.

        CHQ-4: ويُقفل هنا ما يقرؤه قيد السند (المبلغ، الاتجاه، الطرف، العملة)
        متى صار السند مرحّلاً — تغييره كان يجعل اليومية تصف ورقةً غير التي في
        الجدول، بلا أي تعارض ظاهر. التصحيح يمرّ بإلغاء ترحيل السند.
        """
        if self.instance is not None:
            from .services import cheque_document_is_posted

            if cheque_document_is_posted(self.instance) is True:
                changed = [
                    field for field in self._LOCKED_AFTER_POSTING
                    if field in attrs
                    and attrs[field] != getattr(self.instance, field, None)
                ]
                if changed:
                    raise serializers.ValidationError({
                        changed[0]: (
                            'الشيك داخل مستند مرحّل — لا يُعدَّل مبلغه ولا طرفه '
                            'ولا عملته ولا اتجاهه. ألغِ ترحيل المستند، عدّل، '
                            'ثم أعد الترحيل.'
                        ),
                    })
        if self.instance is not None and not (
                'bank' in attrs or 'bank_name' in attrs):
            return attrs
        bank = attrs.get('bank', getattr(self.instance, 'bank', None))
        bank_name = attrs.get(
            'bank_name', getattr(self.instance, 'bank_name', None))
        if not bank and not (bank_name or '').strip():
            raise serializers.ValidationError({
                'bank': 'البنك المسحوب عليه الشيك مطلوب — اخترْه من البنوك '
                        'المسجَّلة أو اكتب اسمه نصاً.',
            })
        return attrs

    def get_bank_display(self, obj):
        return (obj.bank.name if obj.bank_id else None) or obj.bank_name or ''

    def get_bank_branch_display(self, obj):
        return (obj.bank_branch_ref.name if obj.bank_branch_ref_id else None) or obj.bank_branch or ''

    def get_deposit_bank_account_name(self, obj):
        return str(obj.deposit_bank_account) if obj.deposit_bank_account_id else None

    def get_status_label(self, obj):
        from .services import status_label
        return status_label(obj.direction, obj.status)

    def get_allowed_movements(self, obj):
        from .services import allowed_movement_options
        # CHQ-4: إلزام بنك الإيداع مشروطٌ بامتلاك الشركة بنوكاً نشطة — حقيقةٌ
        # واحدة للطلب كله يحقنها الـViewSet، لا استعلامٌ لكل صفّ في القائمة.
        return allowed_movement_options(
            obj,
            has_active_bank_accounts=self.context.get('has_active_bank_accounts'),
        )

    def get_source_document(self, obj):
        from .services import cheque_source_document
        return cheque_source_document(obj)

    def get_needs_document_post(self, obj):
        from .services import cheque_document_is_posted
        # `False` وحدها تعني «مرتبط ولم يُرحَّل»؛ `None` ورقةٌ يتيمة لا تنتظر شيئاً.
        return cheque_document_is_posted(obj) is False


class ChequeMovementSerializer(serializers.ModelSerializer):
    """T-CHQ2: سجل حركة الشيك — كان يُكتب ولا يُقرأ من أي واجهة."""
    movement_type_display = serializers.CharField(
        source='get_movement_type_display', read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)
    # CHQ-3: تسمية الحركة بدلالة الاتجاه — «تحصيل» على ورقةٍ تخرج من حسابنا
    # كانت تقرأ عكس ما حدث. `movement_type_display` يبقى (تسمية الموديل
    # المحايدة) كي لا ينكسر أي مستهلك قائم.
    movement_type_label = serializers.SerializerMethodField(read_only=True)
    # CHQ-3: أي قيد أنتجته هذه الخطوة. **رقم القيد ومرجعه فقط، بلا مبلغه**:
    # سند قبض موزَّع على فاتورتين يشقّ مبلغ الشيك على قيدين (THA-489)، فمبلغ
    # القيد قد لا يساوي مبلغ الشيك — الرابط يقود إلى القيد ليُقرأ كاملاً، ولا
    # يزعم أن هذا القيد «هو قيد مبلغ هذا الشيك».
    journal_number = serializers.SerializerMethodField(read_only=True)
    journal_reference = serializers.SerializerMethodField(read_only=True)
    journal_date = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ChequeMovement
        fields = [
            'id', 'cheque', 'movement_type', 'movement_type_display',
            'movement_type_label', 'journal', 'journal_number',
            'journal_reference', 'journal_date',
            'notes', 'created_at', 'created_by', 'created_by_name',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_username() if obj.created_by_id else None

    def get_movement_type_label(self, obj):
        from .services import movement_label
        return movement_label(obj.cheque.direction, obj.movement_type)

    def get_journal_number(self, obj):
        return f"#{obj.journal_id}" if obj.journal_id else None

    def get_journal_reference(self, obj):
        return obj.journal.reference_type if obj.journal_id else None

    def get_journal_date(self, obj):
        return obj.journal.transaction_date if obj.journal_id else None


class BankBranchSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source='bank.name', read_only=True)

    class Meta:
        model = BankBranch
        fields = ['id', 'bank', 'bank_name', 'name', 'branch_code', 'address', 'phone', 'is_active']
        read_only_fields = ['id', 'bank_name']


class BankSerializer(serializers.ModelSerializer):
    branches = BankBranchSerializer(many=True, read_only=True)
    accounts_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bank
        fields = ['id', 'name', 'code', 'swift_code', 'country', 'notes', 'is_active',
                  'branches', 'accounts_count']
        read_only_fields = ['id', 'branches', 'accounts_count']

    def get_accounts_count(self, obj):
        return obj.accounts.count()


class BankAccountSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source='bank.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)
    currency_code = serializers.CharField(source='currency.Code', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    balance = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BankAccount
        fields = ['id', 'bank', 'bank_name', 'branch', 'branch_name', 'name',
                  'account_number', 'iban', 'currency', 'currency_code',
                  'account', 'account_code', 'is_default', 'is_active', 'notes', 'balance']
        # حساب الشجرة يُنشئه الخادم — لا يُختار من الواجهة.
        read_only_fields = ['id', 'account', 'account_code', 'bank_name', 'branch_name',
                            'currency_code', 'balance']

    def get_balance(self, obj):
        from django.db.models import Sum, DecimalField
        from django.db.models.functions import Coalesce
        money = DecimalField(max_digits=18, decimal_places=2)
        agg = JournalLine.objects.filter(
            account_id=obj.account_id, journal__is_posted=True,
        ).aggregate(
            d=Coalesce(Sum("debit"), 0, output_field=money),
            c=Coalesce(Sum("credit"), 0, output_field=money),
        )
        return str((agg["d"] or 0) - (agg["c"] or 0))


class BankReconciliationSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.SerializerMethodField(read_only=True)
    currency_code = serializers.CharField(source='bank_account.currency.Code', read_only=True)

    class Meta:
        model = BankReconciliation
        fields = ['id', 'bank_account', 'bank_account_name', 'currency_code', 'statement_date',
                  'statement_balance', 'status', 'notes', 'created_at', 'closed_at']
        read_only_fields = ['id', 'bank_account_name', 'currency_code', 'status',
                            'created_at', 'closed_at']

    def get_bank_account_name(self, obj):
        return str(obj.bank_account)


class CashBoxLedgerAccountSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField(source="account.id", read_only=True)
    account_code = serializers.CharField(source="account.code", read_only=True)
    # task16 E16: رصيد الصندوق الحقيقي من دفتر الأستاذ (مدين − دائن للقيود المرحَّلة)
    # — كان العرض يعتمد رصيداً مخزّناً في mirror لا يتحدّث أبداً ⇒ يبقى صفراً.
    balance = serializers.SerializerMethodField()

    class Meta:
        model = CashBoxLedgerAccount
        fields = [
            "id", "external_id", "name", "currency_code", "account_id",
            "account_code", "balance", "is_default", "is_active", "notes",
        ]
        # `external_id` مفتاح توافق يولّده الخادم — لا يُعدَّل بعد الإنشاء وإلا
        # انفصل الصندوق عن وثيقة مرآته. و`is_default` يُضبط بنقطته وحدها
        # لأن وحدانيّته تحتاج معاملة تُصفّر أشقاءه.
        read_only_fields = [
            "id", "account_id", "account_code", "balance", "external_id", "is_default",
        ]

    def get_balance(self, obj):
        from django.db.models import Sum, DecimalField
        from django.db.models.functions import Coalesce
        if not obj.account_id:
            return "0.00"
        agg = JournalLine.objects.filter(
            account_id=obj.account_id, journal__is_posted=True,
        ).aggregate(
            d=Coalesce(Sum("debit"), 0, output_field=DecimalField(max_digits=18, decimal_places=2)),
            c=Coalesce(Sum("credit"), 0, output_field=DecimalField(max_digits=18, decimal_places=2)),
        )
        return str((agg["d"] or 0) - (agg["c"] or 0))


class CashTransferSerializer(serializers.ModelSerializer):
    """T-CASHBOX M6: التحويل مستندٌ يُقرأ — وطرفاه يُمرَّران للخدمة لا للنموذج."""

    from_name = serializers.SerializerMethodField()
    to_name = serializers.SerializerMethodField()

    class Meta:
        model = CashTransfer
        fields = [
            "id", "number", "transfer_date", "amount", "rate", "notes",
            "from_cash_box", "from_bank_account", "to_cash_box", "to_bank_account",
            "from_name", "to_name", "journal", "created_at",
        ]
        read_only_fields = fields

    def _side_name(self, box, bank):
        if box is not None:
            return box.name
        return bank.name if bank is not None else None

    def get_from_name(self, obj):
        return self._side_name(obj.from_cash_box, obj.from_bank_account)

    def get_to_name(self, obj):
        return self._side_name(obj.to_cash_box, obj.to_bank_account)


class CashCountSerializer(serializers.ModelSerializer):
    cash_box_name = serializers.CharField(source="cash_box.name", read_only=True)
    currency_code = serializers.CharField(source="cash_box.currency_code", read_only=True)
    cash_box = TenantScopedPrimaryKeyRelatedField(
        queryset=CashBoxLedgerAccount.objects.all())

    class Meta:
        model = CashCount
        fields = [
            "id", "cash_box", "cash_box_name", "currency_code", "count_date",
            "book_balance", "counted_total", "difference", "denominations",
            "status", "notes", "journal", "created_at",
        ]
        # الدفتري والفرق يحسبهما الخادم لحظة الترحيل — رقمٌ من العميل هنا
        # يجعل الجرد يشهد على نفسه.
        read_only_fields = [
            "id", "book_balance", "difference", "status", "journal", "created_at",
        ]


class ExpenseVoucherSerializer(serializers.ModelSerializer):
    """issue #56 — سند مصروف. القراءة وحدها: الإنشاء يمرّ بـ`create_expense_voucher`
    عبر `ExpenseVoucherViewSet.create` لا بحفظ هذا الـserializer (نمط `CashTransferSerializer`)."""

    expense_account_name = serializers.CharField(source="expense_account.name", read_only=True)
    expense_account_code = serializers.CharField(source="expense_account.code", read_only=True)
    cash_or_bank_account_name = serializers.CharField(
        source="cash_or_bank_account.name", read_only=True, default=None)
    beneficiary_partner_name = serializers.CharField(
        source="beneficiary_partner.name", read_only=True, default=None)
    currency_code = serializers.CharField(source="currency.Code", read_only=True)

    class Meta:
        model = ExpenseVoucher
        fields = [
            "id", "number", "date", "expense_account", "expense_account_name",
            "expense_account_code", "amount", "tax_amount", "currency", "currency_code",
            "exchange_rate", "payment_method", "kind", "cash_or_bank_account",
            "cash_or_bank_account_name", "beneficiary_partner", "beneficiary_partner_name",
            "beneficiary_name", "description", "attachment_url", "journal", "is_posted",
            "created_at",
        ]
        read_only_fields = fields


class RevenueVoucherSerializer(serializers.ModelSerializer):
    """issue #80 — سند إيراد. القراءة وحدها: الإنشاء يمرّ بـ`create_revenue_voucher`
    عبر `RevenueVoucherViewSet.create` لا بحفظ هذا الـserializer (مرآة `ExpenseVoucherSerializer`)."""

    revenue_account_name = serializers.CharField(source="revenue_account.name", read_only=True)
    revenue_account_code = serializers.CharField(source="revenue_account.code", read_only=True)
    cash_or_bank_account_name = serializers.CharField(
        source="cash_or_bank_account.name", read_only=True, default=None)
    payer_partner_name = serializers.CharField(
        source="payer_partner.name", read_only=True, default=None)
    currency_code = serializers.CharField(source="currency.Code", read_only=True)

    class Meta:
        model = RevenueVoucher
        fields = [
            "id", "number", "date", "revenue_account", "revenue_account_name",
            "revenue_account_code", "amount", "tax_amount", "currency", "currency_code",
            "exchange_rate", "payment_method", "kind", "cash_or_bank_account",
            "cash_or_bank_account_name", "payer_partner", "payer_partner_name",
            "payer_name", "description", "attachment_url", "journal", "is_posted",
            "created_at",
        ]
        read_only_fields = fields


class PartnerAccountCodingRuleSerializer(serializers.ModelSerializer):
    """issue #84 — قاعدة ترميز (شركة، طرف) ← حساب. تُكتب من `batch_save_vouchers`
    وحدها؛ هذا الـserializer للقراءة والتعديل (PATCH يغيّر الحساب) والحذف —
    لا POST هنا، فالإنشاء أثرٌ جانبيّ للحفظ الدفعي لا فعلٌ مستقل."""

    partner_name = serializers.CharField(source="partner.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_code = serializers.CharField(source="account.code", read_only=True)

    class Meta:
        model = PartnerAccountCodingRule
        fields = [
            "id", "partner", "partner_name", "account", "account_name",
            "account_code", "updated_at",
        ]
        read_only_fields = ["id", "partner", "partner_name", "account_name", "account_code", "updated_at"]


class ExchangeRateSerializer(serializers.ModelSerializer):
    from_currency_code = serializers.CharField(source='from_currency.Code', read_only=True)
    to_currency_code = serializers.CharField(source='to_currency.Code', read_only=True)

    class Meta:
        model = ExchangeRate
        fields = [
            'id', 'from_currency', 'to_currency',
            'from_currency_code', 'to_currency_code',
            'rate', 'effective_date',
        ]


class FiscalPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalPeriod
        fields = ['id', 'name', 'start_date', 'end_date', 'status', 'is_closed']
        # THA-197: حالة الإقفال تتغيّر عبر `close/` و`reopen/` وحدهما — لا عبر
        # كتابة مباشرة على الحقل.
        read_only_fields = ['id', 'status', 'is_closed']


class TaxRateSerializer(serializers.ModelSerializer):
    tax_account_name = serializers.CharField(source='tax_account.name', read_only=True)
    tax_account_code = serializers.CharField(source='tax_account.code', read_only=True)
    tax_account_type = serializers.CharField(source='tax_account.account_type', read_only=True)

    class Meta:
        model = TaxRate
        fields = [
            'id', 'name', 'code', 'rate',
            'tax_account', 'tax_account_name', 'tax_account_code', 'tax_account_type',
            'direction', 'is_active',
        ]

    def validate(self, attrs):
        """تحقّق من أن اتجاه الضريبة يطابق نوع الحساب.
        - sales → الحساب يجب أن يكون Liability (التزام ضريبي للدولة).
        - purchase → الحساب يجب أن يكون Asset (ضريبة قابلة للاسترداد).
        """
        direction = attrs.get('direction') or (self.instance.direction if self.instance else 'both')
        tax_account = attrs.get('tax_account') or (self.instance.tax_account if self.instance else None)
        if tax_account and direction in ('sales', 'purchase'):
            required = 'Liability' if direction == 'sales' else 'Asset'
            if tax_account.account_type != required:
                raise serializers.ValidationError({
                    'tax_account': (
                        f"نوع الحساب لا يطابق الاتجاه: {direction} يتطلب {required}، "
                        f"لكن الحساب المختار {tax_account.account_type}."
                    ),
                })
        return attrs


# ── الأرصدة الافتتاحية ────────────────────────────────────────────────────
class OpeningBalanceAccountLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = OpeningBalanceAccountLine
        fields = ['id', 'account', 'account_code', 'account_name', 'debit', 'credit', 'notes']


class OpeningBalanceStockLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_name = serializers.SerializerMethodField(read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    value = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OpeningBalanceStockLine
        fields = [
            'id', 'product', 'product_sku', 'product_name',
            'warehouse', 'warehouse_name', 'quantity', 'unit_cost', 'value',
        ]

    def get_product_name(self, obj):
        p = obj.product
        return p.name_ar or p.name_en or p.sku or ''

    def get_value(self, obj):
        return str(
            (Decimal(str(obj.quantity)) * Decimal(str(obj.unit_cost))).quantize(Decimal('0.01'))
        )


class OpeningBalanceAccountLineInputSerializer(serializers.Serializer):
    """بند حساب وارد من الشاشة — الحساب مقيَّد بشركة الطلب عند الكتابة."""

    account = TenantScopedPrimaryKeyRelatedField(queryset=Account.objects.all())
    debit = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=0)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=0)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


class OpeningBalanceStockLineInputSerializer(serializers.Serializer):
    product = TenantScopedPrimaryKeyRelatedField(queryset=Product.objects.all())
    warehouse = TenantScopedPrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4)


class OpeningBalanceLinesInputSerializer(serializers.Serializer):
    """حفظ جماعي لمسودة الافتتاح — الرِّجل الغائبة عن الطلب لا تُمَسّ."""

    start_date = serializers.DateField(required=False, allow_null=True)
    account_lines = OpeningBalanceAccountLineInputSerializer(many=True, required=False)
    stock_lines = OpeningBalanceStockLineInputSerializer(many=True, required=False)
