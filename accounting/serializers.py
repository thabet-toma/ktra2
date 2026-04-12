from rest_framework import serializers
from .models import (
    Account, JournalHeader, JournalLine, Cheque, CostCenter,
    CashBoxLedgerAccount, ExchangeRate, FiscalPeriod, TaxRate,
)
from partners.models import Partner

class AccountSerializer(serializers.ModelSerializer):
    """يُرجع معلومات المورد المرتبط بالحساب (الاسم التجاري / المستعار) إن وُجد."""

    linked_partner = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'parent', 'account_type', 'is_active',
            'linked_partner',
        ]

    def get_linked_partner(self, obj):
        p = (
            Partner.objects.filter(linked_account_id=obj.id)
            .values('id', 'name', 'legal_name')
            .first()
        )
        if not p:
            return None
        return {
            'id': p['id'],
            'trade_name': p['name'] or '',
            'legal_name': p['legal_name'] or '',
        }

class CostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCenter
        fields = '__all__'

class JournalLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    # Use PrimaryKeyRelatedField for strict ID validation
    partner = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(),
        many=False, 
        read_only=False,
        required=False, 
        allow_null=True
    )
    cost_center = serializers.PrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(),
        many=False,
        read_only=False,
        required=False,
        allow_null=True
    )

    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'debit', 'credit', 'partner', 'cost_center', 'description', 'project_id']


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


def build_journal_reference_summary(obj, pay_map=None):
    """ملخص مرجع القيد: رقم الصفقة + اسم المصنع + المورد + رقم الدفعة."""
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


class JournalHeaderListSerializer(serializers.ModelSerializer):
    """قائمة خفيفة بلا أسطر تفصيلية."""

    reference_summary = serializers.SerializerMethodField(read_only=True)
    deal_ref_number = serializers.SerializerMethodField(read_only=True)
    currency_code = serializers.SerializerMethodField(read_only=True)

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
        ]

    def get_currency_code(self, obj):
        return obj.currency.Code if obj.currency_id else None

    def get_reference_summary(self, obj):
        return build_journal_reference_summary(obj, self.context.get("logistics_payments"))

    def get_deal_ref_number(self, obj):
        return get_deal_ref_number(obj, self.context.get("logistics_payments"))


class JournalHeaderSerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)
    reference_summary = serializers.SerializerMethodField(read_only=True)
    deal_ref_number = serializers.SerializerMethodField(read_only=True)
    currency_code = serializers.SerializerMethodField(read_only=True)

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
            'lines',
        ]

    def get_currency_code(self, obj):
        return obj.currency.Code if obj.currency_id else None

    def get_reference_summary(self, obj):
        return build_journal_reference_summary(obj, self.context.get("logistics_payments"))

    def get_deal_ref_number(self, obj):
        return get_deal_ref_number(obj, self.context.get("logistics_payments"))

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
    class Meta:
        model = Cheque
        fields = '__all__'


class CashBoxLedgerAccountSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField(source="account.id", read_only=True)
    account_code = serializers.CharField(source="account.code", read_only=True)

    class Meta:
        model = CashBoxLedgerAccount
        fields = ["id", "external_id", "name", "currency_code", "account_id", "account_code"]
        read_only_fields = ["id", "account_id", "account_code"]


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
        read_only_fields = ['id']


class TaxRateSerializer(serializers.ModelSerializer):
    tax_account_name = serializers.CharField(source='tax_account.name', read_only=True)

    class Meta:
        model = TaxRate
        fields = ['id', 'name', 'code', 'rate', 'tax_account', 'tax_account_name', 'is_active']

