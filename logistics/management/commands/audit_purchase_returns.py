"""تدقيقٌ قراءةً فقط لحالة مرتجعات الشراء التاريخية (تذكرة PRET-M0-AUDIT).

يقيس هذا الأمر حجم مرتجعات الشراء القائمة وأثرها على حسابَي المخزون (1104)
ووسيط الاستلام (2110) وفروق العملة والاستثناءات قبل ترحيل أيّ بنية جديدة:
  S1: أعداد PRET (مرحّل / مسودّة، بأصل / حرّ).
  S2: دائن المخزون في قيد `PURCHASE_RETURN` مقابل كلفة حركات `RETURN_OUT`.
  S3: الحصة المنزاحة من المرتجعات الدولية نحو 1104 مقابل الرصيد المفتوح في 2110.
  S4: فواتير أصلية بلا مدين 2110 ولها كمية غير مستلمة ومرتجع مرحّل.
  S5: المرتجعات المحلية بعملة أجنبية التي تحوّلت مرّتين قبل إصلاح B1.
  S6: استثناءات الإسناد الخلفي لكل زوج (فاتورة أصلية، منتج).
  S7: أعداد المسار القديم (`SalesInvoice.INVOICE_KIND_PURCHASE_RETURN`).
  S8: إجمالي تقدير الانجراف التاريخي في 1104 و2110 (بسطرٍ مستقل لكل حساب) وسطر فائض أساس S5.

**لا يكتب شيئاً** في قاعدة البيانات — استعلامات قراءة وتجميع فقط.

    python manage.py audit_purchase_returns --tenant 1
    python manage.py audit_purchase_returns --limit 20
"""
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Sum

from accounting.services import Account, JournalHeader, JournalLine
from inventory.models import StockMovement
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import (
    GR_IR_ACCOUNT_CODE,
    QTY,
    _is_international_return,
    _resolve_inventory_account,
    _resolve_vat_input_account,
    open_goods_clearing,
    purchase_item_receipt_quantities,
)
from sales.models import SalesInvoice
from tenants.models import Tenant

DEC = Decimal("0.01")
ZERO = Decimal("0.00")
ONE = Decimal("1")
S2_THRESHOLD = Decimal("0.01")
S5_MIN_TOL = Decimal("0.05")
S5_REL_TOL = Decimal("0.001")


def _q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(DEC)


def _fmt(value) -> str:
    return str(_q2(value))


def _qq(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY)


def _fmt_q(value) -> str:
    # الكميات تُطبع بأربع منازل (دقة `QTY`): منزلتان تُخفيان غير مستلم 0.0050.
    return str(_qq(value))


@dataclass
class _TenantMetrics:
    s1_posted: int = 0
    s1_draft: int = 0
    s2_count: int = 0
    s2_signed: Decimal = ZERO
    s2_abs: Decimal = ZERO
    s3_count: int = 0
    s3_confirmed: Decimal = ZERO
    s3_upper: Decimal = ZERO
    s3_rate_ne1: int = 0
    s4_count: int = 0
    s5_count: int = 0
    s5_excess: Decimal = ZERO
    s6_exc: int = 0
    s7_posted: int = 0
    s7_draft: int = 0


class Command(BaseCommand):
    help = (
        "تدقيق قراءة فقط لحالة مرتجعات الشراء التاريخية والانجراف في 1104/2110 "
        "(PRET-M0-AUDIT) — لا يكتب شيئاً."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="معرّف الشركة (افتراضياً كل الشركات).")
        parser.add_argument(
            "--limit", type=int, default=20,
            help="حدّ القوائم الأعلى أثراً في كل قسم (افتراضياً 20).",
        )

    def handle(self, *args, **options):
        limit = max(0, int(options.get("limit") or 0))
        tenants = Tenant.objects.all().order_by("TenantID")
        if options.get("tenant"):
            tenants = tenants.filter(TenantID=options["tenant"])

        grand = _TenantMetrics()
        audited_count = 0
        silent_count = 0

        for tenant in tenants:
            s1 = PurchaseInvoice.objects.filter(tenant=tenant, is_return=True).aggregate(
                posted=Count("id", filter=Q(is_posted=True)),
                draft=Count("id", filter=Q(is_posted=False)),
                with_orig=Count("id", filter=Q(original_invoice_id__isnull=False)),
                without_orig=Count("id", filter=Q(original_invoice_id__isnull=True)),
            )
            s7 = SalesInvoice.objects.filter(
                tenant=tenant, invoice_kind=SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
            ).aggregate(
                total=Count("id"),
                posted=Count("id", filter=Q(status=SalesInvoice.STATUS_POSTED)),
                draft=Count("id", filter=Q(status=SalesInvoice.STATUS_DRAFT)),
            )
            if ((s1["posted"] or 0) + (s1["draft"] or 0)) == 0 and (s7["total"] or 0) == 0:
                silent_count += 1
                continue

            audited_count += 1
            m = self._audit_tenant(tenant, limit, s1=s1, s7=s7)
            grand.s1_posted += m.s1_posted
            grand.s1_draft += m.s1_draft
            grand.s2_count += m.s2_count
            grand.s2_signed = _q2(grand.s2_signed + m.s2_signed)
            grand.s2_abs = _q2(grand.s2_abs + m.s2_abs)
            grand.s3_count += m.s3_count
            grand.s3_confirmed = _q2(grand.s3_confirmed + m.s3_confirmed)
            grand.s3_upper = _q2(grand.s3_upper + m.s3_upper)
            grand.s3_rate_ne1 += m.s3_rate_ne1
            grand.s4_count += m.s4_count
            grand.s5_count += m.s5_count
            grand.s5_excess = _q2(grand.s5_excess + m.s5_excess)
            grand.s6_exc += m.s6_exc
            grand.s7_posted += m.s7_posted
            grand.s7_draft += m.s7_draft

        self.stdout.write(
            f"\nالإجمالي العام ({audited_count} شركة): "
            f"PRET={grand.s1_posted}/{grand.s1_draft} · "
            f"S2={grand.s2_count} (موقّع={_fmt(grand.s2_signed)}, مطلق={_fmt(grand.s2_abs)}) · "
            f"S3={grand.s3_count} (مؤكّد={_fmt(grand.s3_confirmed)}, حدّ_أعلى={_fmt(grand.s3_upper)}, "
            f"سعر≠1={grand.s3_rate_ne1}) · "
            f"S4={grand.s4_count} · "
            f"S5={grand.s5_count} (فائض_أساس S5={_fmt(grand.s5_excess)}) · "
            f"S6_استثناء={grand.s6_exc} · "
            f"S7={grand.s7_posted}/{grand.s7_draft}"
        )
        self.stdout.write(f"شركات بلا مرتجعات: {silent_count}")
        self.stdout.write("تقرير فقط — لم يُكتب شيء في قاعدة البيانات.")

    def _audit_tenant(self, tenant: Tenant, limit: int, *, s1: dict, s7: dict) -> _TenantMetrics:
        m = _TenantMetrics()
        self.stdout.write(f"\nشركة {tenant.TenantID} — {tenant.CompanyName}")

        # ── S1: أعداد PRET ─────────────────────────────────────────────────
        m.s1_posted = s1["posted"] or 0
        m.s1_draft = s1["draft"] or 0
        self.stdout.write(
            f"  S1: مرحّل={m.s1_posted} · مسودّة={m.s1_draft} · "
            f"بأصل={s1['with_orig'] or 0} · حرّ={s1['without_orig'] or 0}"
        )

        posted_returns = list(
            PurchaseInvoice.objects.filter(tenant=tenant, is_return=True, is_posted=True)
            # الشركة محمّلة مع الأصل لأن `open_goods_clearing` تقرأ `invoice.tenant` (بلا استعلام لكل أصل).
            .select_related("original_invoice", "original_invoice__tenant")
            .order_by("id")
        )
        ret_journal_map = self._map_return_journals(tenant, posted_returns)
        inv_account = self._safe_inventory_account(tenant)
        if inv_account is None:
            self.stdout.write(
                "  تحذير: تعذّر تحديد حساب المخزون (1104) لهذه الشركة — "
                "أرقام S2 وS3 أدناه صفرية لا تعكس الواقع."
            )
        inv_credit_by_journal = self._inventory_credits_by_journal(
            tenant, list(ret_journal_map.values()), inv_account,
        )
        # قراءة فقط لحساب 2110 — لا نستعمل `_resolve_gr_ir_account` لأنه يستدعي `get_or_create`.
        gr_ir_acc = Account.objects.filter(tenant=tenant, code=GR_IR_ACCOUNT_CODE).first()

        # نحسب S5 أولاً لاستثناء المرتجعات المتضاعفة بالعملة الأجنبية من S2 (تجنّب التكرار).
        s5_rows, m.s5_excess = self._compute_s5(tenant, posted_returns, ret_journal_map)
        m.s5_count = len(s5_rows)
        s5_flagged_ids = {row[-1] for row in s5_rows}

        # ── S2: دائن المخزون مقابل كلفة حركات RETURN_OUT ──────────────────
        s2_rows, m.s2_signed, m.s2_abs = self._compute_s2(
            tenant, posted_returns, ret_journal_map, inv_credit_by_journal,
            exclude_ids=s5_flagged_ids,
        )
        m.s2_count = len(s2_rows)
        self.stdout.write(
            f"  S2: عدد المتأثرين={m.s2_count} · مستثنى_S5={len(s5_flagged_ids)} · "
            f"موقّع={_fmt(m.s2_signed)} · مطلق={_fmt(m.s2_abs)}"
        )
        for _abs_d, diff, num, credit, mv_cost, _rid in s2_rows[:limit]:
            self.stdout.write(
                f"    {num} · دائن_1104={_fmt(credit)} · كلفة_الحركة={_fmt(mv_cost)} · فرق={_fmt(diff)}"
            )

        # ── S3: المرتجعات الدولية وأثر 2110 المفتوح ─────────────────────────
        intl_total, s3_rows, m.s3_confirmed, m.s3_upper, m.s3_rate_ne1 = self._compute_s3(
            tenant, posted_returns, ret_journal_map, inv_credit_by_journal, gr_ir_acc,
        )
        m.s3_count = len(s3_rows)
        self.stdout.write(
            f"  S3: دولية مرحّلة={intl_total} · فواتير_متأثرة={m.s3_count} · "
            f"سعر≠1={m.s3_rate_ne1} · "
            f"مؤكّد={_fmt(m.s3_confirmed)} · حدّ_أعلى={_fmt(m.s3_upper)}"
        )
        for misrouted, s_val, open_amt, ret_cnt, orig_num, label, _oid in s3_rows[:limit]:
            self.stdout.write(
                f"    {orig_num} · مرتجعات={ret_cnt} · حصة_2110={_fmt(s_val)} · "
                f"مفتوح_2110={_fmt(open_amt)} · منزاح={_fmt(misrouted)} · [{label}]"
            )

        # ── S4: فواتير أصلية قديمة بلا 2110 ولها كمية غير مستلمة ومرتجع ───
        s4_covered, s4_rows = self._compute_s4(tenant, posted_returns, gr_ir_acc)
        m.s4_count = len(s4_rows)
        self.stdout.write(f"  S4: العدد={m.s4_count} · منها_مغطّى_بالحركات={s4_covered}")
        for unreceived, ret_qty, mv_qty, orig_num, _oid in s4_rows[:limit]:
            self.stdout.write(
                f"    {orig_num} · غير_مستلم={_fmt_q(unreceived)} · "
                f"مرتجع={_fmt_q(ret_qty)} · استلام_بالحركات={_fmt_q(mv_qty)}"
            )

        # ── S5: مرتجعات محلية أجنبية متضاعفة قبل B1 ────────────────────────
        self.stdout.write(f"  S5: العدد={m.s5_count} · فائض_الأساس={_fmt(m.s5_excess)}")
        for _abs_ex, excess, ret_num, rate, actual_base, correct_base, _rid in s5_rows[:limit]:
            self.stdout.write(
                f"    {ret_num} · سعر={rate} · فعلي={_fmt(actual_base)} · "
                f"صحيح={_fmt(correct_base)} · فائض={_fmt(excess)}"
            )

        # ── S6: استثناءات الإسناد الخلفي (أصل، منتج) ───────────────────────
        det_count, kind_a, kind_same, kind_b, kind_absent, s6_rows = self._compute_s6(tenant)
        m.s6_exc = len(s6_rows)
        # received_quantity لم يُعبَّأ خلفياً للفواتير المحلية القديمة: أصلٌ أدخل المخزون بحركاته
        # يضخّم «ب» زيفاً، فيُعدّ ويُوسَم دون تغيير التصنيف (القاعدة نفسها التي يطبّقها S4).
        b_covered_ids = self._s6_b_originals_covered(tenant, s6_rows)
        b_covered_count = sum(
            1 for row in s6_rows if "ب:تجاوز_مستلم" in row[5] and row[8] in b_covered_ids
        )
        self.stdout.write(
            f"  S6: حتمي={det_count} · تعدد_أسعار={kind_a} · "
            f"أسطر_متعددة_بسعر_واحد={kind_same} · تجاوز_مستلم={kind_b} · "
            f"منها_ب_أصل_مغطّى_بالحركات={b_covered_count} · "
            f"غير_موجود_بالأصل={kind_absent}"
        )
        for _sev, _gap, orig_num, prod_name, prod_id, label, ret_q, recv_q, oid in s6_rows[:limit]:
            covered_note = (
                " · مغطّى_بالحركات" if "ب:تجاوز_مستلم" in label and oid in b_covered_ids else ""
            )
            self.stdout.write(
                f"    {orig_num} · «{prod_name}» (#{prod_id}) · [{label}] · "
                f"مرتجع={_fmt_q(ret_q)} · مستلم={_fmt_q(recv_q)}{covered_note}"
            )

        # ── S7: المسار القديم SalesInvoice ─────────────────────────────────
        m.s7_posted = s7["posted"] or 0
        m.s7_draft = s7["draft"] or 0
        self.stdout.write(
            f"  S7: قديم (SalesInvoice) مرحّل={m.s7_posted} · "
            f"مسودّة={m.s7_draft} · إجمالي={s7['total'] or 0}"
        )

        # ── S8: تقدير الانجراف التاريخي في 1104 و2110 ─────────────────────
        self.stdout.write(
            f"  S8: انجراف 1104 (Σ S2، بلا مرتجعات S5) موقّع={_fmt(m.s2_signed)} · "
            f"مطلق={_fmt(m.s2_abs)}"
        )
        self.stdout.write(
            f"  S8: انجراف 2110 الدولي (Σ S3) مؤكّد={_fmt(m.s3_confirmed)} · "
            f"حدّ_أعلى={_fmt(m.s3_upper)} · سعر≠1={m.s3_rate_ne1}"
        )
        # مرتجعات S5 مستثناة من S2 فلا يظهر انجرافها في سطر 1104: سطرٌ مستقل كي لا يختفي شيء بصمت.
        self.stdout.write(f"  S8: فائض_أساس S5={_fmt(m.s5_excess)}")

        self.stdout.write(
            f"  ملخّص شركة {tenant.TenantID}: PRET={m.s1_posted}/{m.s1_draft} · "
            f"S2={m.s2_count} (موقّع={_fmt(m.s2_signed)}, مطلق={_fmt(m.s2_abs)}) · "
            f"S3={m.s3_count} (مؤكّد={_fmt(m.s3_confirmed)}, حدّ_أعلى={_fmt(m.s3_upper)}) · "
            f"S4={m.s4_count} · S5={m.s5_count} (فائض_أساس S5={_fmt(m.s5_excess)}) · "
            f"S6_استثناء={m.s6_exc} · S7={m.s7_posted}/{m.s7_draft}"
        )
        return m

    @staticmethod
    def _safe_inventory_account(tenant: Tenant):
        try:
            return _resolve_inventory_account(tenant)
        except ValidationError:
            return None

    @staticmethod
    def _safe_vat_input_account(tenant: Tenant):
        try:
            return _resolve_vat_input_account(tenant)
        except ValidationError:
            return None

    @staticmethod
    def _is_international(ret: PurchaseInvoice) -> bool:
        # القاعدة هي `_is_international_return` نفسها كما تطبّقها `post_purchase_return`:
        # الأصل موجود ودوليّ؛ نوع المرتجع نفسه لا يُعتدّ به (الأصل يحمّل select_related).
        return _is_international_return(ret.original_invoice if ret.original_invoice_id else None)

    @staticmethod
    def _map_return_journals(tenant: Tenant, posted_returns: list[PurchaseInvoice]) -> dict[int, int]:
        if not posted_returns:
            return {}
        ret_ids = [r.id for r in posted_returns]
        ret_jids = [r.journal_id for r in posted_returns if r.journal_id]
        headers = list(
            JournalHeader.objects.filter(
                tenant=tenant, is_posted=True, reference_type="PURCHASE_RETURN",
            )
            .filter(Q(id__in=ret_jids) | Q(reference_id__in=ret_ids))
            .order_by("id")
            .values_list("id", "reference_id")
        )
        valid_jids = {jid for jid, _ in headers}
        # عند تعدّد قيود PURCHASE_RETURN لمرتجعٍ واحد (ولا رابط journal صالح) يُختار أدنى معرّف:
        # الترتيب بـid ثم setdefault يُبقي أول قيد، فالنتيجة حتمية بين التشغيلات.
        by_ref: dict[int, int] = {}
        for jid, ref_id in headers:
            if ref_id is not None:
                by_ref.setdefault(ref_id, jid)
        mapping: dict[int, int] = {}
        for r in posted_returns:
            if r.journal_id and r.journal_id in valid_jids:
                mapping[r.id] = r.journal_id
            elif r.id in by_ref:
                mapping[r.id] = by_ref[r.id]
        return mapping

    @staticmethod
    def _inventory_credits_by_journal(
        tenant: Tenant, journal_ids: list[int], inv_account,
    ) -> dict[int, Decimal]:
        if not journal_ids or inv_account is None:
            return {}
        rows = (
            JournalLine.objects.filter(
                tenant=tenant, journal_id__in=journal_ids, account_id=inv_account.id,
            )
            .values("journal_id")
            .annotate(total=Sum("base_credit"))
        )
        return {row["journal_id"]: _q2(row["total"]) for row in rows}

    @staticmethod
    def _originals_with_debit_2110(
        tenant: Tenant, originals: list[PurchaseInvoice], gr_ir_acc,
    ) -> set[int]:
        if not originals or gr_ir_acc is None:
            return set()
        orig_ids = [o.id for o in originals]
        orig_jids = [o.journal_id for o in originals if o.journal_id]
        lines = list(
            JournalLine.objects.filter(
                tenant=tenant,
                account_id=gr_ir_acc.id,
                debit__gt=0,
                journal__is_posted=True,
            )
            .filter(
                Q(journal_id__in=orig_jids)
                | Q(journal__reference_type="PURCHASE_INVOICE", journal__reference_id__in=orig_ids)
            )
            .values_list("journal_id", "journal__reference_type", "journal__reference_id")
        )
        jids_with_2110 = {jid for jid, _, _ in lines}
        refs_with_2110 = {
            ref_id for _, rtype, ref_id in lines
            if rtype == "PURCHASE_INVOICE" and ref_id is not None
        }
        return {
            o.id for o in originals
            if (o.journal_id and o.journal_id in jids_with_2110) or o.id in refs_with_2110
        }

    def _compute_s2(
        self,
        tenant: Tenant,
        posted_returns: list[PurchaseInvoice],
        ret_journal_map: dict[int, int],
        inv_credit_by_journal: dict[int, Decimal],
        *,
        exclude_ids: set[int] | None = None,
    ):
        excluded = exclude_ids or set()
        eligible = [r for r in posted_returns if r.id not in excluded]
        if not eligible:
            return [], ZERO, ZERO
        ret_ids = [r.id for r in eligible]
        mv_costs = {
            row["reference_id"]: _q2(row["total"])
            for row in StockMovement.objects.filter(
                tenant=tenant,
                movement_type="RETURN_OUT",
                reference_type="PURCHASE_RETURN",
                reference_id__in=ret_ids,
            )
            .values("reference_id")
            .annotate(total=Sum("total_cost"))
        }
        rows = []
        signed_total = ZERO
        abs_total = ZERO
        for r in eligible:
            jid = ret_journal_map.get(r.id)
            credit = inv_credit_by_journal.get(jid, ZERO) if jid else ZERO
            mv_cost = mv_costs.get(r.id, ZERO)
            diff = _q2(credit - mv_cost)
            abs_d = abs(diff)
            if abs_d > S2_THRESHOLD:
                rows.append((abs_d, diff, r.invoice_number, credit, mv_cost, r.id))
                signed_total = _q2(signed_total + diff)
                abs_total = _q2(abs_total + abs_d)
        rows.sort(key=lambda x: (-x[0], x[5]))
        return rows, signed_total, abs_total

    def _compute_s3(
        self,
        tenant: Tenant,
        posted_returns: list[PurchaseInvoice],
        ret_journal_map: dict[int, int],
        inv_credit_by_journal: dict[int, Decimal],
        gr_ir_acc,
    ):
        # المنزاح هنا يقع أيضاً ضمن فرق S2 للمرتجعات الدولية (دائن 1104 مقابل كلفة الحركة)؛
        # لكنهما حسابان مختلفان في S8 (1104 مقابل 2110) فلا ازدواج في أيّ مجموع.
        intl = [r for r in posted_returns if self._is_international(r)]
        if not intl or gr_ir_acc is None:
            return len(intl), [], ZERO, ZERO, 0

        returns_by_orig: dict[int, list[PurchaseInvoice]] = {}
        orig_by_id: dict[int, PurchaseInvoice] = {}
        for r in intl:
            if r.original_invoice_id and r.original_invoice.tenant_id == tenant.TenantID:
                orig_by_id[r.original_invoice_id] = r.original_invoice
                returns_by_orig.setdefault(r.original_invoice_id, []).append(r)
        if not orig_by_id:
            return len(intl), [], ZERO, ZERO, 0

        originals = list(orig_by_id.values())
        orig_ids = [o.id for o in originals]
        orig_jids = [o.journal_id for o in originals if o.journal_id]
        vat_acc = self._safe_vat_input_account(tenant)

        # استعلام واحد مجمّع لكل الأصول لحساب D2110 وDG بعمود debit نفسه الذي تقرؤه open_goods_clearing.
        dg_filter = Q(debit__gt=0)
        if vat_acc is not None:
            dg_filter &= ~Q(account_id=vat_acc.id)

        agg_rows = (
            JournalLine.objects.filter(
                tenant=tenant,
                journal__is_posted=True,
                journal__reference_type="PURCHASE_INVOICE",
                debit__gt=0,
            )
            .filter(Q(journal_id__in=orig_jids) | Q(journal__reference_id__in=orig_ids))
            .values("journal_id", "journal__reference_id")
            .annotate(
                d2110=Sum("debit", filter=Q(account_id=gr_ir_acc.id)),
                dg=Sum("debit", filter=dg_filter),
            )
            .order_by("journal_id")
        )
        by_jid: dict[int, tuple[Decimal, Decimal]] = {}
        by_ref: dict[int, tuple[Decimal, Decimal]] = {}
        # عند تعدّد قيود PURCHASE_INVOICE لأصلٍ واحد (ولا رابط journal صالح) يُختار أدنى معرّف:
        # الترتيب بـjournal_id ثم setdefault يُبقي أول قيد، كما في `_map_return_journals`.
        for row in agg_rows:
            pair = (Decimal(str(row["d2110"] or 0)), Decimal(str(row["dg"] or 0)))
            by_jid[row["journal_id"]] = pair
            if row["journal__reference_id"] is not None:
                by_ref.setdefault(row["journal__reference_id"], pair)

        cand_originals = []
        d2110_dg_by_orig: dict[int, tuple[Decimal, Decimal]] = {}
        for o in originals:
            d2110, dg = (
                by_jid[o.journal_id] if o.journal_id and o.journal_id in by_jid
                else by_ref.get(o.id, (Decimal("0"), Decimal("0")))
            )
            if d2110 > 0:
                cand_originals.append(o)
                d2110_dg_by_orig[o.id] = (d2110, dg)

        if not cand_originals:
            return len(intl), [], ZERO, ZERO, 0

        cand_ids = [o.id for o in cand_originals]
        grn_orig_ids = set(
            JournalLine.objects.filter(
                tenant=tenant,
                account_id=gr_ir_acc.id,
                credit__gt=0,
                journal__is_posted=True,
                journal__reference_type="PURCHASE_GRN",
                journal__reference_id__in=cand_ids,
            ).values_list("journal__reference_id", flat=True)
        )
        # استلامٌ بلا قيد GRN (مسار الإرسالية القديم `sync_import_receipt_from_shipment_stock` يضبط
        # `received_quantity` وحدها): البضاعة دخلت المخزن فخصم 1104 كان صحيحاً، فلا يُوسَم «مؤكّد».
        received_orig_ids = {
            row["invoice_id"]
            for row in PurchaseInvoiceItem.objects.filter(
                invoice__tenant=tenant, invoice_id__in=cand_ids,
            )
            .values("invoice_id")
            .annotate(recv=Sum("received_quantity"))
            if (row["recv"] or 0) > 0
        }

        rows = []
        confirmed_total = ZERO
        upper_total = ZERO
        for o in cand_originals:
            d2110, dg = d2110_dg_by_orig[o.id]
            rets = returns_by_orig[o.id]
            if dg > 0:
                raw_s = sum(
                    (
                        inv_credit_by_journal.get(ret_journal_map[r.id], ZERO) * d2110 / dg
                        if r.id in ret_journal_map
                        else ZERO
                    )
                    for r in rets
                )
                s_val = _q2(raw_s)
            else:
                s_val = ZERO
            if s_val <= ZERO:
                continue
            _acc, _total, open_amt = open_goods_clearing(o)
            open_amt = _q2(open_amt)
            misrouted = min(s_val, open_amt)
            if misrouted <= ZERO:
                continue
            if o.id in grn_orig_ids or o.id in received_orig_ids:
                label = "حدّ_أعلى"
                upper_total = _q2(upper_total + misrouted)
            else:
                label = "مؤكّد"
                confirmed_total = _q2(confirmed_total + misrouted)
            rows.append((misrouted, s_val, open_amt, len(rets), o.invoice_number, label, o.id))

        rows.sort(key=lambda x: (-x[0], -x[1], x[6]))

        # S3 يخلط base_credit المرتجع بأعمدة debit/credit، ولا يصحّ ذلك إلا بسعر 1: العدّاد يبيّن هل صحّ.
        rate_ne1 = 0
        if rows:
            affected = [o for o in cand_originals if o.id in {row[6] for row in rows}]
            affected_ids = [o.id for o in affected]
            affected_jids = [o.journal_id for o in affected if o.journal_id]
            odd_headers = list(
                JournalHeader.objects.filter(
                    tenant=tenant, is_posted=True, reference_type="PURCHASE_INVOICE",
                )
                .filter(Q(id__in=affected_jids) | Q(reference_id__in=affected_ids))
                .exclude(exchange_rate=1)
                .values_list("id", "reference_id")
            )
            odd_jids = {jid for jid, _ in odd_headers}
            odd_refs = {ref_id for _, ref_id in odd_headers if ref_id is not None}
            rate_ne1 = sum(
                1 for o in affected
                if (o.journal_id and o.journal_id in odd_jids) or o.id in odd_refs
            )
        return len(intl), rows, confirmed_total, upper_total, rate_ne1

    def _compute_s4(
        self,
        tenant: Tenant,
        posted_returns: list[PurchaseInvoice],
        gr_ir_acc,
    ):
        orig_ids = sorted({r.original_invoice_id for r in posted_returns if r.original_invoice_id})
        if not orig_ids:
            return 0, []
        originals = list(
            PurchaseInvoice.objects.filter(tenant=tenant, is_return=False, id__in=orig_ids)
            .order_by("id")
        )
        has_2110 = self._originals_with_debit_2110(tenant, originals, gr_ir_acc)
        no_2110 = [o for o in originals if o.id not in has_2110]
        if not no_2110:
            return 0, []
        no_2110_ids = [o.id for o in no_2110]

        # القاعدة الوحيدة للاستلام في النظام: `purchase_item_receipt_quantities` (بدقة QTY، الباقي مقصوص عند الصفر).
        ordered_by_inv: dict[int, Decimal] = {}
        unreceived_by_inv: dict[int, Decimal] = {}
        for item in PurchaseInvoiceItem.objects.filter(
            invoice__tenant=tenant,
            invoice_id__in=no_2110_ids,
            product_id__isnull=False,
        ).only("invoice_id", "quantity", "received_quantity"):
            ordered, _received, remaining = purchase_item_receipt_quantities(item)
            ordered_by_inv[item.invoice_id] = ordered_by_inv.get(item.invoice_id, ZERO) + ordered
            unreceived_by_inv[item.invoice_id] = (
                unreceived_by_inv.get(item.invoice_id, ZERO) + remaining
            )

        cand_ids = [o.id for o in no_2110 if _qq(unreceived_by_inv.get(o.id)) > 0]
        if not cand_ids:
            return 0, []

        ret_sums = {
            row["invoice__original_invoice_id"]: Decimal(str(row["ret_qty"] or 0))
            for row in PurchaseInvoiceItem.objects.filter(
                invoice__tenant=tenant,
                invoice__is_return=True,
                invoice__is_posted=True,
                invoice__original_invoice_id__in=cand_ids,
            )
            .values("invoice__original_invoice_id")
            .annotate(ret_qty=Sum("quantity"))
        }
        mv_received = self._movement_received(tenant, cand_ids)

        rows = []
        covered_count = 0
        for o in no_2110:
            unreceived = _qq(unreceived_by_inv.get(o.id))
            if unreceived <= 0:
                continue
            ordered = _qq(ordered_by_inv.get(o.id))
            mv_qty = mv_received.get(o.id, _qq(0))
            if ordered > 0 and mv_qty >= ordered:
                covered_count += 1
            ret_qty = _qq(ret_sums.get(o.id))
            rows.append((unreceived, ret_qty, mv_qty, o.invoice_number, o.id))
        rows.sort(key=lambda x: (-x[0], x[4]))
        return covered_count, rows

    @staticmethod
    def _movement_received(tenant: Tenant, original_ids: list[int]) -> dict[int, Decimal]:
        # كمية الاستلام بالحركات لكل أصل: Σ حركات IN / PURCHASE_INVOICE بدقة QTY (استعلام تجميعي واحد).
        if not original_ids:
            return {}
        return {
            row["reference_id"]: _qq(row["total"])
            for row in StockMovement.objects.filter(
                tenant=tenant,
                movement_type="IN",
                reference_type="PURCHASE_INVOICE",
                reference_id__in=original_ids,
            )
            .values("reference_id")
            .annotate(total=Sum("quantity"))
        }

    def _s6_b_originals_covered(self, tenant: Tenant, s6_rows: list) -> set[int]:
        # الأصول ذات صفوف «ب» المغطّاة بالحركات بقاعدة S4: Σ الحركات ≥ Σ المطلوب لبنود المنتجات.
        b_oids = sorted({row[8] for row in s6_rows if "ب:تجاوز_مستلم" in row[5]})
        if not b_oids:
            return set()
        # الكمية DecimalField بأربع منازل، فتقريب المجموع إلى QTY يساوي جمع `purchase_item_receipt_quantities`.
        ordered_by_inv = {
            row["invoice_id"]: _qq(row["ordered"])
            for row in PurchaseInvoiceItem.objects.filter(
                invoice__tenant=tenant,
                invoice_id__in=b_oids,
                product_id__isnull=False,
            )
            .values("invoice_id")
            .annotate(ordered=Sum("quantity"))
        }
        mv_received = self._movement_received(tenant, b_oids)
        covered = set()
        for oid in b_oids:
            ordered = ordered_by_inv.get(oid, _qq(0))
            if ordered > 0 and mv_received.get(oid, _qq(0)) >= ordered:
                covered.add(oid)
        return covered

    def _compute_s5(
        self,
        tenant: Tenant,
        posted_returns: list[PurchaseInvoice],
        ret_journal_map: dict[int, int],
    ):
        candidates = []
        for r in posted_returns:
            if self._is_international(r):
                continue
            rate = Decimal(str(r.exchange_rate or 1))
            if rate != ONE and rate > 0 and r.id in ret_journal_map:
                candidates.append(r)
        if not candidates:
            return [], ZERO

        cand_ids = [r.id for r in candidates]
        cand_jids = [ret_journal_map[r.id] for r in candidates]

        items_by_inv: dict[int, list[dict]] = {}
        for row in PurchaseInvoiceItem.objects.filter(
            invoice__tenant=tenant, invoice_id__in=cand_ids,
        ).values(
            "invoice_id", "quantity", "unit_price", "is_taxable", "vat_percent",
        ):
            items_by_inv.setdefault(row["invoice_id"], []).append(row)

        ap_by_journal = {
            row["journal_id"]: (_q2(row["debit"]), _q2(row["base_debit"]))
            for row in JournalLine.objects.filter(
                tenant=tenant,
                journal_id__in=cand_jids,
                partner_id__isnull=False,
                debit__gt=0,
            )
            .values("journal_id")
            .annotate(debit=Sum("debit"), base_debit=Sum("base_debit"))
        }

        rows = []
        excess_total = ZERO
        for r in candidates:
            inv_net = ZERO
            inv_vat = ZERO
            for it in items_by_inv.get(r.id, ()):
                qty = Decimal(str(it["quantity"] or 0))
                if qty <= 0:
                    continue
                line_net = (qty * Decimal(str(it["unit_price"] or 0))).quantize(DEC)
                vat_pct = Decimal(str(it["vat_percent"] or 0)) if it["is_taxable"] else ZERO
                inv_net += line_net
                inv_vat += (line_net * vat_pct / Decimal("100")).quantize(DEC)
            # nominal_gross يطابق حساب الإجمالي الاسمي في `post_purchase_return` ويجب تعديله معها عند تغيّرها.
            nominal_gross = (inv_net + inv_vat).quantize(DEC)
            if nominal_gross <= ZERO:
                continue

            jid = ret_journal_map[r.id]
            if jid not in ap_by_journal:
                continue
            actual_debit, actual_base = ap_by_journal[jid]
            rate = Decimal(str(r.exchange_rate or 1))
            doubled_debit = _q2(nominal_gross * rate)
            tol = max(S5_MIN_TOL, _q2(doubled_debit * S5_REL_TOL))
            if abs(actual_debit - doubled_debit) <= tol and abs(actual_debit - nominal_gross) > tol:
                correct_base = doubled_debit
                excess = _q2(actual_base - correct_base)
                rows.append((abs(excess), excess, r.invoice_number, rate, actual_base, correct_base, r.id))
                excess_total = _q2(excess_total + excess)

        rows.sort(key=lambda x: (-x[0], x[6]))
        return rows, excess_total

    def _compute_s6(self, tenant: Tenant):
        ret_pairs = list(
            PurchaseInvoiceItem.objects.filter(
                invoice__tenant=tenant,
                invoice__is_return=True,
                invoice__is_posted=True,
                invoice__original_invoice_id__isnull=False,
                invoice__original_invoice__tenant=tenant,
                product_id__isnull=False,
                quantity__gt=0,
            )
            .values("invoice__original_invoice_id", "product_id", "product__name_ar")
            .annotate(ret_qty=Sum("quantity"))
        )
        if not ret_pairs:
            return 0, 0, 0, 0, 0, []

        orig_ids = sorted({p["invoice__original_invoice_id"] for p in ret_pairs})
        prod_ids = sorted({p["product_id"] for p in ret_pairs})

        orig_info: dict[tuple[int, int], dict] = {}
        for row in PurchaseInvoiceItem.objects.filter(
            invoice__tenant=tenant, invoice_id__in=orig_ids, product_id__in=prod_ids,
        ).values(
            "invoice_id", "product_id", "unit_price", "received_quantity",
            "invoice__invoice_number", "product__name_ar", "name",
        ):
            key = (row["invoice_id"], row["product_id"])
            entry = orig_info.setdefault(key, {
                "orig_num": row["invoice__invoice_number"],
                "prod_name": row["product__name_ar"] or row["name"] or f"#{row['product_id']}",
                "prices": set(),
                "line_count": 0,
                "received": Decimal("0"),
            })
            entry["prices"].add(Decimal(str(row["unit_price"] or 0)))
            entry["line_count"] += 1
            entry["received"] += Decimal(str(row["received_quantity"] or 0))

        # احتياط: اسم الفاتورة إذا غاب البند المقابل على الأصلية
        orig_nums = dict(
            PurchaseInvoice.objects.filter(tenant=tenant, id__in=orig_ids)
            .values_list("id", "invoice_number")
        )

        deterministic = 0
        kind_a = 0
        kind_same = 0
        kind_b = 0
        kind_absent = 0
        exceptions = []
        for p in ret_pairs:
            oid = p["invoice__original_invoice_id"]
            pid = p["product_id"]
            # بدقة QTY قبل المقارنة: القيمة المطبوعة هي القيمة المقارَنة نفسها.
            ret_q = _qq(p["ret_qty"])
            info = orig_info.get((oid, pid))
            if info is None:
                kind_absent += 1
                orig_num = orig_nums.get(oid, f"#{oid}")
                prod_name = p["product__name_ar"] or f"#{pid}"
                exceptions.append((
                    1,
                    ret_q,
                    orig_num,
                    prod_name,
                    pid,
                    "غير_موجود_بالأصل",
                    ret_q,
                    Decimal("0"),
                    oid,
                ))
                continue

            recv_q = _qq(info["received"])
            exc_a = len(info["prices"]) > 1
            exc_same = info["line_count"] > 1 and len(info["prices"]) == 1
            exc_b = ret_q > recv_q
            if not exc_a and not exc_same and not exc_b:
                deterministic += 1
                continue
            if exc_a:
                kind_a += 1
            if exc_same:
                kind_same += 1
            if exc_b:
                kind_b += 1
            kinds = []
            if exc_a:
                kinds.append("أ:تعدد_أسعار")
            if exc_same:
                kinds.append("أسطر_متعددة_بسعر_واحد")
            if exc_b:
                kinds.append("ب:تجاوز_مستلم")
            exceptions.append((
                int(exc_a) + int(exc_same) + int(exc_b),
                ret_q - recv_q,
                info["orig_num"],
                info["prod_name"],
                pid,
                "+".join(kinds),
                ret_q,
                recv_q,
                oid,
            ))

        exceptions.sort(key=lambda x: (-x[0], -x[1], x[8], x[4]))
        return deterministic, kind_a, kind_same, kind_b, kind_absent, exceptions
