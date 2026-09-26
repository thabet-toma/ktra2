import json
import logging

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.plans import enforce_limits
from core.tenant_utils import get_tenant
from tenants.models import Currency, Tenant
from .models import CustomerNote, Partner, PartnerBankAccount, is_creditor_party
from .serializers import (
    CustomerNoteSerializer, PartnerBankAccountSerializer, PartnerListSerializer,
    PartnerSerializer, find_partner_with_similar_bank_account, normalize_identifier,
)
from django.utils import timezone

logger = logging.getLogger(__name__)


#: أصناف صفحة الأطراف الدائنة — المورد يُقسَم بنطاقه، وبقية الأطراف بنوعها.
#: «مورد محلي + وكيل شحن» لا يُعبَّر عنه بـ`partner_type` و`supplier_scope` معاً:
#: نطاق الوكيل فارغ فيلتقطه فلتر «غير المصنّف».
PARTNER_KINDS = {
    "supplier_local": Q(partner_type="Supplier", supplier_scope="local"),
    "supplier_international": Q(partner_type="Supplier", supplier_scope="international"),
    "supplier_unscoped": Q(partner_type="Supplier", supplier_scope=""),
    "FreightForwarder": Q(partner_type="FreightForwarder"),
    "CustomsBroker": Q(partner_type="CustomsBroker"),
    "LocalTransporter": Q(partner_type="LocalTransporter"),
    "Carrier": Q(partner_type="Carrier"),
}


def _party_accruals_total(partner):
    """(مجموع مستحقّات الطرف الدائن المرحّلة، تاريخ آخرها) — التخليص والشحن والنقل."""
    from logistics.domain.party_accruals import party_accrued_total
    return party_accrued_total(partner.tenant_id, partner.id)


def _party_accrual_invoice_rows(partner) -> list[dict]:
    """مستحقّات التخليص والشحن والنقل المرحّلة على الطرف — «فواتير» المخلّص والوكيل
    والناقل في كرته. المدفوع والمتبقّي من `accrual_status` (القيود والسندات الموزَّعة)،
    والرقم وسمُ الشحنة، والرابط إلى شحنتها (`shipment_id`)."""
    from decimal import Decimal
    from core.payments import document_payment_summary
    from logistics.domain.party_accruals import ACCRUAL_ANCHOR_TYPE, party_open_accruals

    rows = []
    for row in party_open_accruals(partner.tenant_id, partner.id, include_settled=True):
        due = Decimal(row["due"])
        summary = document_payment_summary(
            due, Decimal(row["paid"]) + Decimal(row["allocated"]))
        rows.append({
            "document_type": ACCRUAL_ANCHOR_TYPE[row["kind"]],
            "document_id": row["id"],
            "document_number": row["label"],
            "shipment_id": row["shipment_id"],
            "date": row["date"],
            "grand_total": str(due),
            "is_posted": True,
            "amount_paid": str(summary["amount_paid"]),
            "remaining_balance": str(summary["remaining_balance"]),
            "payment_status": summary["payment_status"],
            "payment_status_display": summary["payment_status_display"],
        })
    rows.sort(key=lambda r: (r["date"] or "", r["document_id"]), reverse=True)
    return rows


def _csv_param(value) -> list[str]:
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


class PartnerViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Partner.objects.all().order_by('-created_at')
    serializer_class = PartnerSerializer
    search_fields = ['name', 'legal_name', 'email', 'phone', 'tax_number']

    def get_serializer_class(self):
        if self.action in {"list", "lookup"}:
            return PartnerListSerializer
        return PartnerSerializer

    def _get_tenant(self):
        return get_tenant(self.request)

    @action(detail=True, methods=["get"], url_path="balance")
    def balance(self, request, pk=None):
        """task18 DEF-C1: رصيد الشريك الحالي من القيود المرحَّلة + الرصيد المتوقع
        بعد عملية مقترحة (?proposed_total=). للعميل: مدين−دائن؛ للمورد: دائن−مدين.
        تُمكِّن شاشتي البيع/الشراء من عرض «الرصيد قبل/بعد» الفاتورة.
        """
        from decimal import Decimal
        from accounting.services import partner_posted_balance
        partner = self.get_object()
        debit, credit = partner_posted_balance(partner.tenant_id, partner.id)
        is_supplier = is_creditor_party(partner)
        open_balance = (credit - debit) if is_supplier else (debit - credit)
        try:
            proposed = Decimal(str(request.query_params.get("proposed_total", "0")))
        except Exception:
            proposed = Decimal("0")
        return Response({
            "partner": partner.id,
            "partner_type": partner.partner_type,
            # الواجهة تقرأ به «له/عليه» — موجبُ الدائن له، وموجبُ العميل عليه.
            "is_creditor": is_supplier,
            "debit": str(debit),
            "credit": str(credit),
            "open_balance": str(open_balance),
            "proposed_total": str(proposed),
            "projected_balance": str(open_balance + proposed),
        })

    # ── FEAT-4: Party (customer/supplier) profile ────────────────
    @action(detail=True, methods=["get"], url_path="surplus")
    def surplus(self, request, pk=None):
        """فائض الطرف «تحت الحساب» مصدراً مصدراً — سنداتٌ وإشعاراتٌ مسوّية غير موزَّعة ولا
        مسترَدّة. تقرؤه نافذة الاسترداد في بطاقته (`sales/services/party_surplus.py`)."""
        from sales.services.party_surplus import party_surplus_rows

        partner = self.get_object()
        return Response({"rows": party_surplus_rows(partner.tenant_id, partner)})

    @action(detail=True, methods=["get"], url_path="profile")
    def profile(self, request, pk=None):
        """رأس بطاقة الشريك: الرصيد Dr/Cr + إجمالي المبيعات/المشتريات + المتبقي
        + تاريخ آخر معاملة. تُطابق الأرصدة المصدر القانوني (القيود المرحَّلة)."""
        from decimal import Decimal
        from django.db.models import Sum, Max
        from accounting.services import partner_posted_balance
        from sales.models import SalesInvoice
        from logistics.models import PurchaseInvoice

        partner = self.get_object()
        is_supplier = is_creditor_party(partner)
        debit, credit = partner_posted_balance(partner.tenant_id, partner.id)
        balance = (credit - debit) if is_supplier else (debit - credit)

        sales_agg = SalesInvoice.objects.filter(
            tenant_id=partner.tenant_id, customer_id=partner.id,
            status=SalesInvoice.STATUS_POSTED,
        ).aggregate(total=Sum("grand_total"), last=Max("invoice_date"))
        from logistics.services import annotate_purchase_supplier_share
        # الدولية بحصّة المورد لا بالمحمَّل — حصص الوكيل والمخلّص والناقل ليست مشترياتٍ منه.
        purch_agg = annotate_purchase_supplier_share(PurchaseInvoice.objects.filter(
            tenant_id=partner.tenant_id, partner_id=partner.id, is_posted=True,
        )).aggregate(total=Sum("supplier_share"), last=Max("invoice_date"))
        total_purchases = purch_agg["total"] or Decimal("0")
        last_dates = [d for d in (sales_agg["last"], purch_agg["last"]) if d]
        if is_supplier:
            # المخلّص والوكيل والناقل: «مشترياتهم» مستحقّاتُ التخليص والشحن والنقل.
            accrued, last_accrual = _party_accruals_total(partner)
            total_purchases += accrued
            if last_accrual:
                last_dates.append(last_accrual)
        last_txn = max(last_dates).isoformat() if last_dates else None
        # الدائن: رصيدٌ لنا لم يُستهلك — «دفعات تحت الحساب» و«فائض» (مستحقٌّ خُفِّض بعد
        # دفعه) — رقمان في رأس كشفه؛ الرصيد نفسه لا يتغيّر بهما.
        on_account = {"on_account": Decimal("0"), "surplus": Decimal("0")}
        if is_supplier:
            from logistics.domain.party_accruals import party_on_account_summary
            on_account = party_on_account_summary(partner.tenant_id, partner.id)

        # عميل: رصيد موجب = مدين له علينا (Dr/ذمم مدينة). مورد: رصيد موجب =
        # دائن نحن مدينون له (Cr/ذمم دائنة). الإشارة السالبة تعكس الجهة.
        natural = "Cr" if is_supplier else "Dr"
        opposite = "Dr" if is_supplier else "Cr"
        balance_side = natural if balance >= 0 else opposite

        return Response({
            "id": partner.id,
            "name": partner.name,
            "partner_type": partner.partner_type,
            "phone": partner.phone,
            "email": partner.email,
            "debit": str(debit),
            "credit": str(credit),
            "balance": str(balance),
            "balance_side": balance_side,
            "outstanding_balance": str(abs(balance)),
            "total_sales": str(sales_agg["total"] or Decimal("0")),
            "total_purchases": str(total_purchases),
            "last_transaction_date": last_txn,
            "on_account_payments": str(on_account["on_account"]),
            "accrual_surplus": str(on_account["surplus"]),
        })

    @action(detail=True, methods=["get"], url_path="statement")
    def statement(self, request, pk=None):
        """كشف حساب الشريك (الأستاذ) — Debit/Credit + رصيد جارٍ، مُرقَّم."""
        from accounting.services import partner_account_statement
        partner = self.get_object()
        is_supplier = is_creditor_party(partner)
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (TypeError, ValueError):
            offset = 0
        ordering = request.query_params.get("ordering", "newest")
        # THA-128: تبويب «المال» يطلب حركات التسوية وحدها من الكشف نفسه.
        only_payments = str(
            request.query_params.get("only_payments", "")).lower() in ("1", "true", "yes")
        # كشف بعملةٍ أجنبية (`?currency=USD`) من `amount_currency`؛ بلاه بالشيكل كما كان.
        currency = str(request.query_params.get("currency", "")).strip().upper()
        if currency and not (len(currency) == 3 and currency.isalpha()):
            return Response({"error": "رمز العملة غير صالح."}, status=400)
        return Response(partner_account_statement(
            tenant_id=partner.tenant_id, partner_id=partner.id,
            is_supplier=is_supplier, limit=limit, offset=offset, ordering=ordering,
            only_payments=only_payments, currency=currency or None))

    @action(detail=True, methods=["get"], url_path="stock-movements")
    def stock_movements(self, request, pk=None):
        """حركات مخزون الشريك مجمَّعةً تحت مستندها — تبويب «المال» في كرته.

        `get_object` هو حارس العزل: شريك شركةٍ أخرى لا يُبلَغ أصلاً، والخدمة
        تُنطَّق فوقه بـ`tenant_id` — العدد تسريبٌ أيضاً لا الأسماء وحدها.
        """
        from inventory.services import partner_stock_movements
        partner = self.get_object()
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (TypeError, ValueError):
            offset = 0
        return Response(partner_stock_movements(
            tenant_id=partner.tenant_id, partner_id=partner.id,
            limit=limit, offset=offset))

    @action(detail=True, methods=["get"], url_path="invoices")
    def invoices(self, request, pk=None):
        """فواتير الشريك (بيع للعميل + شراء للمورد) — كلٌّ قابل للنقر.

        حالة الدفع (مدفوعة/جزئياً/غير مدفوعة) تُشتقّ من نفس مصدر شاشتَي الفواتير
        (`core.payments.document_payment_summary`) فلا تختلف البطاقة عن القائمة.
        """
        from sales.models import SalesInvoice
        from logistics.models import PurchaseInvoice
        from core.payments import document_payment_summary
        from logistics.services import annotate_purchase_invoice_payment_summary
        partner = self.get_object()
        out = []
        for inv in SalesInvoice.objects.filter(
            tenant_id=partner.tenant_id, customer_id=partner.id,
        ).order_by("-invoice_date", "-id")[:200]:
            summary = document_payment_summary(inv.grand_total, inv.amount_paid)
            out.append({
                "document_type": "SALES_INVOICE",
                "document_id": inv.id,
                "document_number": inv.invoice_number,
                "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "grand_total": str(inv.grand_total),
                "is_posted": inv.status == SalesInvoice.STATUS_POSTED,
                "amount_paid": str(summary["amount_paid"]),
                "remaining_balance": str(summary["remaining_balance"]),
                "payment_status": summary["payment_status"],
                "payment_status_display": summary["payment_status_display"],
            })
        purchases = annotate_purchase_invoice_payment_summary(
            PurchaseInvoice.objects.filter(
                tenant_id=partner.tenant_id, partner_id=partner.id,
            )
        ).order_by("-invoice_date", "-id")[:200]
        for inv in purchases:
            # المجموع الواجب على فاتورة الشراء = الإجمالي + الرسوم (list_payable_total).
            summary = document_payment_summary(inv.list_payable_total, inv.list_amount_paid)
            out.append({
                "document_type": "PURCHASE_INVOICE",
                "document_id": inv.id,
                "document_number": inv.invoice_number,
                "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "grand_total": str(inv.list_payable_total),
                "is_posted": bool(inv.is_posted),
                "amount_paid": str(summary["amount_paid"]),
                "remaining_balance": str(summary["remaining_balance"]),
                "payment_status": summary["payment_status"],
                "payment_status_display": summary["payment_status_display"],
            })
        if is_creditor_party(partner):
            out.extend(_party_accrual_invoice_rows(partner))
        return Response(out)

    def get_queryset(self):
        # task11 M7: القراءة كانت بلا فلترة tenant — موردو/زبائن كل الشركات
        # كانوا يظهرون لأي شركة. .none() عند غياب الشركة حتى لا يتسرب شيء.
        tenant = self._get_tenant()
        if not tenant:
            return Partner.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        # الموقوف يختفي من القوائم والمنتقيات فقط — كرته وتعديله وكشفه تبقى.
        if (
            self.action in {"list", "lookup", "kind_counts"}
            and self.request.query_params.get("include_inactive") not in {"1", "true"}
        ):
            qs = qs.filter(is_active=True)
        # النوع والنطاق يقبلان قيمة أو قائمة مفصولة بفاصلة.
        partner_types = _csv_param(self.request.query_params.get("partner_type"))
        if partner_types:
            qs = qs.filter(partner_type__in=partner_types)
        # T-IMPOFFER: فصل المورد الدولي عن المحلي. غير المصنَّف ('') يظهر في
        # الجانبين — الفصل الجديد لا يُخفي مورداً قائماً عن شاشته المعتادة.
        scopes = _csv_param(self.request.query_params.get("supplier_scope"))
        if scopes:
            qs = qs.filter(Q(supplier_scope__in=scopes) | Q(supplier_scope=""))
        kinds = [k for k in _csv_param(self.request.query_params.get("kinds")) if k in PARTNER_KINDS]
        if kinds:
            kinds_q = Q()
            for kind in kinds:
                kinds_q |= PARTNER_KINDS[kind]
            qs = qs.filter(kinds_q)
        assigned_price_tier = self.request.query_params.get("assigned_price_tier")
        if assigned_price_tier:
            qs = qs.filter(assigned_price_tier=assigned_price_tier)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(tax_number__icontains=search)
            )
        return qs

    @action(detail=False, methods=["get"], url_path="lookup")
    def lookup(self, request):
        """Bounded raw-array contract for pickers that do not render pages."""
        try:
            limit = int(request.query_params.get("limit", 200))
        except (TypeError, ValueError):
            limit = 200
        limit = min(max(limit, 1), 500)
        rows = self.get_queryset().order_by("name", "id")[:limit]
        return Response(self.get_serializer(rows, many=True).data)

    @action(detail=False, methods=["get"], url_path="kind-counts")
    def kind_counts(self, request):
        """عدّاد كل صنف في صفحة الأطراف الدائنة — يحترم البحث والموقوفين لا الأصناف المختارة."""
        from django.db.models import Count

        counts = self.get_queryset().order_by().aggregate(
            **{kind: Count("id", filter=q) for kind, q in PARTNER_KINDS.items()}
        )
        return Response(counts)

    @action(detail=False, methods=["post"], url_path="bulk-scope")
    def bulk_scope(self, request):
        """تصنيف جماعي للموردين محليين/دوليين — موردو هذه الشركة وحدهم.

        النطاق لا يمسّ الحساب المحاسبي (الأب 2101 للمورد أيّاً كان نطاقه)، فـ`update`
        واحد بلا إشارات الحفظ.
        """
        scope = request.data.get("supplier_scope")
        if scope not in {"local", "international"}:
            raise ValidationError({"supplier_scope": "النطاق يجب أن يكون محلياً أو دولياً."})
        try:
            ids = [int(i) for i in request.data.get("ids") or []]
        except (TypeError, ValueError):
            raise ValidationError({"ids": "معرّفات غير صالحة."})
        tenant = self._get_tenant()
        if not tenant or not ids:
            raise ValidationError({"ids": "لم يُختر أي مورد."})
        updated = Partner.objects.filter(
            tenant=tenant, pk__in=ids, partner_type="Supplier",
        ).update(supplier_scope=scope, updated_at=timezone.now())
        logger.info(
            "partner.bulk_scope tenant=%s scope=%s requested=%s updated=%s user=%s",
            tenant.TenantID, scope, len(ids), updated, getattr(request.user, "pk", None),
        )
        return Response({"updated": updated})

    @action(detail=True, methods=["get"], url_path="payment-defaults")
    def payment_defaults(self, request, pk=None):
        """بيانات الطرف القابلة لإعادة الاستخدام عند إنشاء سند/شيك.

        رقم حساب الطرف يُستخدم فقط للشيك الوارد منه. الشيك الصادر للمورد يُسحب
        من حساب الشركة، لذلك نعيد اسم المستفيد دون نسخ حساب المورد إلى الشيك.
        """
        partner = self.get_object()
        direction = request.query_params.get("direction", "Incoming")
        if direction not in {"Incoming", "Outgoing"}:
            raise ValidationError({"direction": "اتجاه الشيك غير صالح."})
        try:
            currency_id = int(request.query_params.get("currency", ""))
        except (TypeError, ValueError):
            currency_id = None

        accounts = list(
            partner.bank_accounts.filter(is_active=True)
            .select_related("currency")
            .order_by("-is_default", "id")
        )
        selected = None
        if direction == "Incoming":
            matching = [a for a in accounts if not currency_id or a.currency_id == currency_id]
            selected = next((a for a in matching if a.is_default), None)
            if selected is None and len(matching) == 1:
                selected = matching[0]
            if selected is None and not currency_id:
                selected = next((a for a in accounts if a.is_default), None)

        beneficiary = next(
            (a.beneficiary_name for a in accounts if a.is_default and a.beneficiary_name),
            None,
        )
        return Response({
            "partner_id": partner.id,
            "partner_name": partner.name,
            "legal_name": partner.legal_name,
            "direction": direction,
            "payee_name": (
                (selected.beneficiary_name if selected else None)
                or beneficiary or partner.legal_name or partner.name
            ),
            "bank_accounts": PartnerBankAccountSerializer(accounts, many=True).data,
            "selected_bank_account": (
                PartnerBankAccountSerializer(selected).data if selected else None
            ),
        })

    def _handle_bank_accounts(self, partner, bank_accounts_data, tenant):
        """
        Synchronizes bank accounts for a partner.
        bank_accounts_data can be a JSON string or a list.
        """
        if isinstance(bank_accounts_data, str):
            try:
                if not bank_accounts_data or bank_accounts_data.strip() == "":
                    bank_accounts_data = []
                else:
                    bank_accounts_data = json.loads(bank_accounts_data)
            except (ValueError, TypeError):
                bank_accounts_data = []

        if not isinstance(bank_accounts_data, list):
            raise ValidationError({"bank_accounts": "قائمة الحسابات البنكية غير صالحة."})

        normalized = []
        seen_numbers = set()
        default_count = 0
        existing_ids = set(partner.bank_accounts.values_list("id", flat=True))
        for acc_data in bank_accounts_data:
            if not isinstance(acc_data, dict):
                raise ValidationError({"bank_accounts": "بيانات الحساب البنكي غير صالحة."})
            bank_name = str(acc_data.get("bank_name") or "").strip()
            account_number = str(acc_data.get("account_number") or "").strip()
            if not bank_name and not account_number and len(bank_accounts_data) == 1:
                continue
            if not bank_name or not account_number:
                raise ValidationError({
                    "bank_accounts": "اسم البنك ورقم الحساب مطلوبان لكافة الحسابات المضافة.",
                })
            # T-DUPID: المقارنة بالصورة المطبَّعة — «0012-300» و«0012300» رقم واحد.
            normalized_number = normalize_identifier(account_number)
            if normalized_number in seen_numbers:
                raise ValidationError({"bank_accounts": "رقم الحساب البنكي مكرر في البطاقة."})
            seen_numbers.add(normalized_number)
            owner = find_partner_with_similar_bank_account(
                getattr(tenant, "TenantID", None), account_number,
                exclude_partner_id=partner.id,
            )
            if owner:
                logger.info(
                    "partner.duplicate_bank_account tenant=%s value=%r existing=%s",
                    getattr(tenant, "TenantID", None), account_number, owner[0],
                )
                raise ValidationError({
                    "bank_accounts": (
                        f"رقم الحساب البنكي «{account_number}» مسجّل للطرف "
                        f"«{owner[1]}» (#{owner[0]}) — لا يُقبل رقم مطابق أو شبيه."
                    ),
                })
            try:
                curr_id = int(acc_data.get("currency"))
            except (ValueError, TypeError):
                raise ValidationError({
                    "bank_accounts": f"يجب تحديد عملة صالحة للحساب البنكي: {bank_name}",
                })
            if not Currency.objects.filter(pk=curr_id).exists():
                raise ValidationError({
                    "bank_accounts": f"عملة الحساب البنكي غير موجودة: {bank_name}",
                })
            acc_id = acc_data.get("id")
            if acc_id not in (None, ""):
                try:
                    acc_id = int(acc_id)
                except (ValueError, TypeError):
                    raise ValidationError({"bank_accounts": "معرّف الحساب البنكي غير صالح."})
                if acc_id not in existing_ids:
                    raise ValidationError({
                        "bank_accounts": "الحساب البنكي لا يتبع هذه البطاقة.",
                    })
            is_active = bool(acc_data.get("is_active", True))
            is_default = bool(acc_data.get("is_default", False))
            if is_default and not is_active:
                raise ValidationError({
                    "bank_accounts": "الحساب البنكي الافتراضي يجب أن يكون فعالاً.",
                })
            default_count += int(is_default)
            normalized.append({
                "id": acc_id,
                "bank_name": bank_name,
                "account_number": account_number,
                "branch_name": str(acc_data.get("branch_name") or "").strip(),
                "iban": str(acc_data.get("iban") or "").strip(),
                "swift_code": str(acc_data.get("swift_code") or "").strip(),
                "bank_address": str(acc_data.get("bank_address") or "").strip(),
                "beneficiary_name": str(acc_data.get("beneficiary_name") or "").strip(),
                "currency_id": curr_id,
                "is_active": is_active,
                "is_default": is_default,
            })
        if default_count > 1:
            raise ValidationError({"bank_accounts": "يجب اختيار حساب بنكي افتراضي واحد فقط."})
        if normalized and default_count == 0:
            first_active = next((a for a in normalized if a["is_active"]), None)
            if first_active:
                first_active["is_default"] = True

        provided_ids = [a["id"] for a in normalized if a["id"]]
        partner.bank_accounts.exclude(id__in=provided_ids).delete()
        for account_data in normalized:
            acc_id = account_data.pop("id")
            if acc_id:
                PartnerBankAccount.objects.filter(id=acc_id, partner=partner).update(
                    tenant=tenant, **account_data,
                )
            else:
                PartnerBankAccount.objects.create(
                    tenant=tenant, partner=partner, **account_data,
                )

    def _handle_attachments(self, partner, data, tenant):
        """
        Saves Cloudinary images and documents to SystemAttachment.
        """
        from core.models import SystemAttachment
        
        # Mapping from frontend keys to file types
        field_map = {
            'image_path': 'Profile Image',
            'image_url': 'Image',
            'document_url': 'Document'
        }

        for field, file_type in field_map.items():
            value = data.get(field)
            if value and isinstance(value, str) and value.startswith('http'):
                # Check if this specific URL is already attached to this partner
                if not SystemAttachment.objects.filter(
                    tenant=tenant,
                    related_table='partners',
                    related_id=partner.id,
                    file_path=value
                ).exists():
                    SystemAttachment.objects.create(
                        tenant=tenant,
                        related_table='partners',
                        related_id=partner.id,
                        file_type=file_type,
                        file_path=value
                    )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        # T-PLANLIMITS: عدد العملاء والموردين المسموح به من خطة الشركة.
        enforce_limits(tenant, 'partners.records')

        # Prepare partner data
        partner_data = request.data.copy()

        # Create partner
        serializer = self.get_serializer(data=partner_data)
        serializer.is_valid(raise_exception=True)
        partner = serializer.save(tenant=tenant)

        # Handle bank accounts sync
        bank_accounts_data = request.data.get('bank_accounts', [])
        self._handle_bank_accounts(partner, bank_accounts_data, tenant)

        # Handle attachments (Cloudinary links)
        self._handle_attachments(partner, request.data, tenant)

        logger.info(
            "partner.create id=%s tenant=%s type=%s bank_accounts=%s user=%s",
            partner.id, tenant.TenantID, partner.partner_type,
            partner.bank_accounts.count(), getattr(request.user, "pk", None),
        )
        return Response(self._with_account_warning(partner), status=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Prepare partner data
        partner_data = request.data.copy()

        # Update partner
        serializer = self.get_serializer(instance, data=partner_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        partner = serializer.save()
                
        # Handle bank accounts sync
        if 'bank_accounts' in request.data:
            bank_accounts_data = request.data.get('bank_accounts', [])
            self._handle_bank_accounts(partner, bank_accounts_data, tenant)

        # Handle attachments (Cloudinary links)
        self._handle_attachments(partner, request.data, tenant)

        logger.info(
            "partner.update id=%s tenant=%s type=%s bank_accounts=%s user=%s",
            partner.id, tenant.TenantID, partner.partner_type,
            partner.bank_accounts.count(), getattr(request.user, "pk", None),
        )
        return Response(self._with_account_warning(partner))

    #: ما يُحذف مع الطرف — بياناته هو لا حركاته: حساباته البنكية وملاحظاته وسجلّ
    #: نشاطه وقواعد ترميزه وربط أصنافه وعروض أسعاره؛ وإعداد «الزبون الافتراضي»
    #: يُفرَّغ (SET_NULL). أيّ علاقة أخرى تحمل صفّاً تمنع.
    DELETE_OWNED = frozenset({
        "partners.PartnerBankAccount", "partners.CustomerNote",
        "core.ActivityLogPartner", "accounting.PartnerAccountCodingRule",
        "inventory.SupplierProduct", "sales.CustomerProductQuote",
        "sales.SalesSettings",
    })

    #: أسماء الحركات في رسالة رفض الحذف — ما لا تسمية له يُعرض باسم النموذج.
    DELETE_BLOCKER_LABELS = {
        "accounting.JournalLine": "قيود", "accounting.Cheque": "شيكات",
        "accounting.ExpenseVoucher": "سندات مصروف", "accounting.RevenueVoucher": "سندات إيراد",
        "inventory.StockMovement": "حركات مخزون",
        "sales.SalesInvoice": "فواتير مبيعات", "sales.SalesQuotation": "عروض أسعار",
        "sales.SalesOrder": "طلبيات", "sales.DeliveryOrder": "سندات تسليم",
        "sales.CustomerPayment": "سندات قبض", "sales.SupplierPayment": "سندات صرف",
        "sales.CreditDebitNote": "إشعارات دائن/مدين",
        "logistics.PurchaseInvoice": "فواتير شراء", "logistics.PurchaseOrder": "أوامر شراء",
        "logistics.GoodsReceipt": "سندات استلام", "logistics.SupplierQuotation": "عروض موردين",
        "logistics.LogisticsDeal": "صفقات استيراد", "logistics.LogisticsShipment": "شحنات",
        "logistics.LogisticsClearance": "تخليصات", "logistics.LogisticsClearancePayment": "دفعات تخليص",
        "logistics.LocalShipment": "إرساليات محلية",
    }

    def _delete_blockers(self, partner) -> list[str]:
        """العلاقات التي تحمل حركات للطرف — تُقرأ من `_meta` فلا تفوت علاقةٌ تُضاف لاحقاً.

        `ProtectedError` وحده لا يكفي حارساً: القيود والتخليصات والشحنات تشير
        للطرف بـ`SET_NULL` فيمرّ الحذف ويفقد القيدُ طرفه بصمت.
        """
        from accounting.api import account_has_journal_lines

        blockers = []
        for rel in partner._meta.related_objects:
            if rel.related_model._meta.label in self.DELETE_OWNED:
                continue
            if rel.related_model._default_manager.filter(**{rel.field.name: partner}).exists():
                label = rel.related_model._meta.label
                name = self.DELETE_BLOCKER_LABELS.get(label, str(rel.related_model._meta.verbose_name))
                if name not in blockers:
                    blockers.append(name)
        if "قيود" not in blockers and partner.linked_account_id and account_has_journal_lines(partner.linked_account_id):
            blockers.append("قيود على حسابه")
        return blockers

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        from django.db.models import ProtectedError, RestrictedError
        from accounting.api import delete_account_if_unused

        partner = self.get_object()
        blockers = self._delete_blockers(partner)
        if blockers:
            logger.info("partner.delete_refused id=%s blockers=%s", partner.id, blockers)
            return Response(
                {"detail": f"عليه حركات ({'، '.join(blockers)}) — أوقفه بدل حذفه.", "blockers": blockers},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account_id = partner.linked_account_id
        try:
            partner.delete()
        except (ProtectedError, RestrictedError):
            return Response(
                {"detail": "عليه حركات — أوقفه بدل حذفه."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account_deleted = delete_account_if_unused(account_id) if account_id else False
        logger.info(
            "partner.delete id=%s tenant=%s account=%s account_deleted=%s user=%s",
            kwargs.get("pk"), partner.tenant_id, account_id, account_deleted,
            getattr(request.user, "pk", None),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _with_account_warning(self, partner) -> dict:
        """ردّ الحفظ + `account_warning` حين بقي الطرف بلا حساب ذمم سليم.

        `sync_partner_accounting` تبتلع أخطاءها كي لا يسقط حفظ الطرف — فكان
        الناقل يُحفظ بلا حساب (2109 غائب) ولا يعلم أحد حتى يُرحَّل سنده على 2101.
        """
        from accounting.api import partner_account_problem

        partner.refresh_from_db()
        data = self.get_serializer(partner).data
        problem = partner_account_problem(partner)
        if problem:
            logger.warning("partner.account_problem id=%s: %s", partner.id, problem)
            data["account_warning"] = problem
        return data


class CustomerNoteViewSet(viewsets.ModelViewSet):
    """ملاحظات/تذكيرات الأطراف والأهداف العامة — CRUD مُنطاق بالشركة.

    قائمة مفلترة بـ ?partner=<id>. تذكيرات مستحقة عبر reminders-due/ لمولّد
    إشعارات الموقع (يُنشئ إشعاراً عند حلول يوم التذكير).
    """
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = CustomerNoteSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return CustomerNote.objects.none()
        qs = CustomerNote.objects.filter(tenant=tenant).select_related('partner').order_by('-created_at')
        partner_id = self.request.query_params.get('partner')
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        target_type = self.request.query_params.get('target_type')
        target_id = self.request.query_params.get('target_id')
        if target_type:
            qs = qs.filter(target_type=target_type)
        if target_id:
            qs = qs.filter(target_id=target_id)
        return qs

    @action(detail=False, methods=["get"], url_path="alerts")
    def alerts(self, request):
        """ملاحظات «عاجل» غير المنجزة التي حلّ موعدها (أو تأخّر) لطرف بعينه.

        تُعرَض لكل مستخدم يفتح معاملة لهذا الطرف — عميلاً كان أو مورداً — لا
        لصاحب الملاحظة وحده. بلا ?partner= لا تُرجَع نتائج (الاستدعاء دائماً
        مربوط بطرف المعاملة).
        """
        from datetime import date
        tenant = get_tenant(request)
        partner_id = request.query_params.get('partner')
        if not tenant or not partner_id:
            return Response([])
        qs = CustomerNote.objects.filter(
            tenant=tenant, partner_id=partner_id, is_done=False,
            priority=CustomerNote.PRIORITY_URGENT,
            remind_on__isnull=False, remind_on__lte=timezone.localdate(),
        ).order_by('remind_on', 'id')
        return Response([
            {
                'id': n.id,
                'title': n.title,
                'body': n.body,
                'remind_on': n.remind_on.isoformat(),
                'priority': n.priority,
                'priority_display': n.get_priority_display(),
            }
            for n in qs
        ])

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({'tenant': 'لا يوجد شركة محددة.'})
        note = serializer.save(
            tenant=tenant,
            created_by=self.request.user if self.request.user.is_authenticated else None,
        )
        logger.info(
            'customer_note.create id=%s partner=%s target=%s:%s tenant=%s remind_on=%s',
            note.id, note.partner_id, note.target_type, note.target_id,
            tenant.TenantID, note.remind_on,
        )

    @action(detail=False, methods=["get"], url_path="reminders-due")
    def reminders_due(self, request):
        """تذكيرات مستحقة اليوم أو قبله وغير منجزة — يستهلكها مولّد الإشعارات."""
        from datetime import date
        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        qs = CustomerNote.objects.filter(
            tenant=tenant, is_done=False,
            remind_on__isnull=False, remind_on__lte=timezone.localdate(),
        ).select_related('partner').order_by('remind_on')
        return Response([
            {
                'id': n.id,
                'title': n.title,
                'remind_on': n.remind_on.isoformat(),
                'partner_id': n.partner_id,
                'partner_name': n.partner.name if n.partner else '',
                'target_type': n.target_type,
                'target_id': n.target_id,
                'target_label': n.target_label or (n.partner.name if n.partner else ''),
                'target_path': n.target_path or (
                    f'/partners/{n.partner_id}?tab=customer_notes' if n.partner_id else ''
                ),
            }
            for n in qs
        ])

