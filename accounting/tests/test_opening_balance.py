"""T119-1 — الأرصدة الافتتاحية: القيد الموحّد وبضاعة أول المدة وعكسهما.

يثبت أن `accounting/opening_balance.py`:
  1. يُنتج **قيداً واحداً متوازناً** بمرجع `OPENING_BALANCE` مؤرَّخاً بيوم واحد
     قبل تاريخ بدء التشغيل، وسطر موازنته على «3300».
  2. يجعل رصيد حسابات المخزون في الأستاذ **مساوياً بالرقم** لمجموع
     (كمية × تكلفة) ولإجمالي تقرير «تقييم المخزون» — معيار المالك الأصلي.
  3. لا يسمح بقيد افتتاحي ثانٍ إلا بعد عكس الأول صراحةً، ويعكس حركات المخزون
     مع القيد، ويرفض العكس إن بيعت بضاعة الافتتاح.
  4. يرفض الحسابات التي تأتي أرقامها من رِجل أخرى (ذمم/مخزون/3300/حساب طرف).
  5. يفشل بلا حالة جزئية إن لم تكن الفترة المالية مفتوحة عند تاريخ القيد.
  6. معزول بالشركة في القراءة والترحيل معاً.
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.test import APIClient

from accounting.models import (
    Account, JournalHeader, JournalLine, OpeningBalance,
)
from accounting.opening_balance import (
    OPENING_REFERENCE_TYPE,
    get_or_create_opening,
    opening_balance_summary,
    post_opening_balance,
    resolve_opening_offset_account,
    save_opening_lines,
    unpost_opening_balance,
)
from accounting.services import create_fiscal_year
from core.reports._framework import run_report
from inventory.models import Product, StockMovement, Warehouse
from inventory.services import record_stock_movement
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

D = Decimal

START_DATE = datetime.date(2026, 3, 1)
ENTRY_DATE = datetime.date(2026, 2, 28)


def _company(name: str, username: str):
    owner = User.objects.create_user(username=username, password="x")
    tenant = create_company(name, owner)
    create_fiscal_year(tenant, 2026)
    warehouse = Warehouse.objects.filter(tenant=tenant).first()
    product = Product.objects.create(
        tenant=tenant, sku=f"OB-{username}", name_ar="صنف افتتاحي",
        quantity_on_hand=D("0"), avg_cost=D("0"),
    )
    return tenant, owner, warehouse, product


@pytest.fixture
def env():
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant, owner, warehouse, product = _company("شركة الافتتاح", "opening")
    return tenant, owner, warehouse, product


def _acc(tenant, code):
    return Account.objects.get(tenant=tenant, code=code)


def _fill_draft(tenant, warehouse, product, *, cash="5000", loan="2000",
                qty="10", unit_cost="30"):
    """مسودة نموذجية: نقدية مدينة · قرض دائن · ١٠ وحدات بتكلفة ٣٠."""
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=START_DATE,
        account_lines=[
            {'account': _acc(tenant, '1101'), 'debit': D(cash), 'credit': D('0')},
            {'account': _acc(tenant, '2102'), 'debit': D('0'), 'credit': D(loan)},
        ],
        stock_lines=[
            {'product': product, 'warehouse': warehouse,
             'quantity': D(qty), 'unit_cost': D(unit_cost)},
        ],
    )
    return opening


def _journal(tenant, opening):
    return JournalHeader.objects.get(
        tenant=tenant,
        reference_type=OPENING_REFERENCE_TYPE,
        reference_id=opening.id,
    )


def _totals(journal):
    lines = JournalLine.objects.filter(journal=journal)
    debit = sum((D(str(l.debit)) for l in lines), D('0'))
    credit = sum((D(str(l.credit)) for l in lines), D('0'))
    return debit, credit


# ── (أ) قيد واحد متوازن مؤرَّخ بيوم قبل البدء ─────────────────────────────
def test_post_creates_one_balanced_journal_dated_day_before_start(env):
    tenant, owner, warehouse, product = env
    opening = _fill_draft(tenant, warehouse, product)

    post_opening_balance(opening, user=owner)
    opening.refresh_from_db()

    assert opening.status == OpeningBalance.STATUS_POSTED
    assert opening.entry_date == ENTRY_DATE == START_DATE - datetime.timedelta(days=1)
    journals = JournalHeader.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE)
    assert journals.count() == 1
    journal = journals.first()
    assert opening.journal_id == journal.id
    assert journal.is_posted is True
    assert journal.transaction_date == ENTRY_DATE
    debit, credit = _totals(journal)
    assert debit == credit


# ── (ب) الأستاذ == مجموع (كمية × تكلفة) == إجمالي تقييم المخزون ───────────
def test_inventory_gl_equals_stock_value_equals_valuation_report(env):
    tenant, owner, warehouse, product = env
    opening = _fill_draft(tenant, warehouse, product, qty="10", unit_cost="30")

    post_opening_balance(opening, user=owner)
    journal = _journal(tenant, opening)

    # 1) رصيد حسابات المخزون في القيد
    inventory_accounts = Account.objects.filter(tenant=tenant, sub_type='inventory')
    gl_inventory = sum(
        (D(str(l.debit)) - D(str(l.credit))
         for l in JournalLine.objects.filter(
             journal=journal, account__in=inventory_accounts)),
        D('0'),
    )
    # 2) مجموع (كمية × تكلفة) من بنود الافتتاح
    lines_value = sum(
        (D(str(l.quantity)) * D(str(l.unit_cost)) for l in opening.stock_lines.all()),
        D('0'),
    )
    # 3) إجمالي تقرير «تقييم المخزون» نفسه (لا إعادة حسابه هنا)
    report = run_report('stock-valuation', tenant.TenantID, {})
    valuation_total = D(report['totals']['value'])

    assert gl_inventory == D('300.00')
    assert gl_inventory == lines_value
    assert lines_value == valuation_total

    product.refresh_from_db()
    assert product.quantity_on_hand == D('10.0000')
    assert product.avg_cost == D('30.0000')
    movement = StockMovement.objects.get(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE, reference_id=opening.id)
    assert movement.movement_date == ENTRY_DATE
    assert movement.warehouse_id == warehouse.id


# ── (ج) 3300 يحمل الفرق والقيد يتوازن ────────────────────────────────────
def test_offset_account_carries_the_plug(env):
    tenant, owner, warehouse, product = env
    opening = _fill_draft(tenant, warehouse, product, cash="5000", loan="2000",
                          qty="10", unit_cost="30")

    summary = opening_balance_summary(tenant)
    # 5000 مدين + 300 مخزون − 2000 دائن = 3300 صافي حقوق ملكية افتتاحية
    assert summary['totals']['equity_plug'] == D('3300.00')

    post_opening_balance(opening, user=owner)
    journal = _journal(tenant, opening)
    offset = resolve_opening_offset_account(tenant.TenantID)
    assert offset.code == '3300'
    plug_line = JournalLine.objects.get(journal=journal, account=offset)
    assert plug_line.credit == D('3300.00')
    assert plug_line.debit == D('0.00')
    debit, credit = _totals(journal)
    assert debit == credit == D('5300.00')


def test_plug_flips_to_debit_when_liabilities_exceed_assets(env):
    """التزامات تفوق الأصول ⇒ حقوق ملكية افتتاحية سالبة: 3300 مدين."""
    tenant, owner, warehouse, product = env
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=START_DATE,
        account_lines=[
            {'account': _acc(tenant, '1101'), 'debit': D('1000'), 'credit': D('0')},
            {'account': _acc(tenant, '2102'), 'debit': D('0'), 'credit': D('2500')},
        ],
        stock_lines=[],
    )
    post_opening_balance(opening, user=owner)
    offset = resolve_opening_offset_account(tenant.TenantID)
    plug_line = JournalLine.objects.get(journal=_journal(tenant, opening), account=offset)
    assert plug_line.debit == D('1500.00')
    assert plug_line.credit == D('0.00')


# ── (د) لا قيد افتتاحي ثانٍ إلا بعد عكس صريح ─────────────────────────────
def test_second_post_rejected_until_unposted(env):
    tenant, owner, warehouse, product = env
    opening = _fill_draft(tenant, warehouse, product)
    post_opening_balance(opening, user=owner)

    with pytest.raises(DjangoValidationError) as exc:
        post_opening_balance(opening, user=owner)
    assert "مرحّل" in str(exc.value)

    unpost_opening_balance(opening, user=owner)
    opening.refresh_from_db()
    assert opening.status == OpeningBalance.STATUS_DRAFT

    post_opening_balance(opening, user=owner)
    opening.refresh_from_db()
    assert opening.status == OpeningBalance.STATUS_POSTED
    assert JournalHeader.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE).count() == 1


# ── (هـ) العكس يحذف القيد ويعيد المخزون، ويُرفض إن بيعت البضاعة ──────────
def test_unpost_removes_journal_and_reverses_stock(env):
    tenant, owner, warehouse, product = env
    opening = _fill_draft(tenant, warehouse, product)
    post_opening_balance(opening, user=owner)

    unpost_opening_balance(opening, user=owner)

    opening.refresh_from_db()
    assert opening.status == OpeningBalance.STATUS_DRAFT
    assert opening.journal_id is None
    assert not JournalHeader.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE).exists()
    assert not StockMovement.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE).exists()
    product.refresh_from_db()
    assert product.quantity_on_hand == D('0.0000')
    # البنود تبقى — العكس يُعيد المستند مسودةً قابلة للتصحيح لا يمحوه
    assert opening.account_lines.count() == 2
    assert opening.stock_lines.count() == 1


def test_unpost_refused_when_opening_stock_already_sold(env):
    tenant, owner, warehouse, product = env
    opening = _fill_draft(tenant, warehouse, product)
    post_opening_balance(opening, user=owner)
    # بيع لاحق استهلك بضاعة الافتتاح
    record_stock_movement(
        product=product, movement_type='OUT', quantity=D('4'),
        reference_type='SALE', reference_id=7701,
        movement_date=datetime.date(2026, 3, 5), tenant=tenant,
    )

    with pytest.raises(DjangoValidationError) as exc:
        unpost_opening_balance(opening, user=owner)
    assert "7701" in str(exc.value)

    # لم يُحذف شيء — إجهاض ذرّي
    opening.refresh_from_db()
    assert opening.status == OpeningBalance.STATUS_POSTED
    assert JournalHeader.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE).exists()
    assert StockMovement.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE).exists()


# ── (و) الحسابات الممنوعة ────────────────────────────────────────────────
@pytest.mark.parametrize("code,fragment", [
    ('1103', 'الأطراف'),   # ذمم مدينة
    ('2101', 'الأطراف'),   # ذمم دائنة
    ('1104', 'المخزون'),   # مخزون
])
def test_forbidden_sub_type_accounts_rejected(env, code, fragment):
    tenant, owner, warehouse, product = env
    opening = get_or_create_opening(tenant)
    with pytest.raises(DjangoValidationError) as exc:
        save_opening_lines(
            opening,
            start_date=START_DATE,
            account_lines=[{'account': _acc(tenant, code),
                            'debit': D('100'), 'credit': D('0')}],
        )
    message = str(exc.value)
    assert fragment in message
    assert 'يضاعف الرصيد' in message
    assert opening.account_lines.count() == 0


def test_offset_account_itself_rejected(env):
    tenant, owner, warehouse, product = env
    offset = resolve_opening_offset_account(tenant.TenantID)
    opening = get_or_create_opening(tenant)
    with pytest.raises(DjangoValidationError) as exc:
        save_opening_lines(
            opening,
            start_date=START_DATE,
            account_lines=[{'account': offset, 'debit': D('100'), 'credit': D('0')}],
        )
    assert 'حساب موازنة القيد' in str(exc.value)


def test_partner_linked_account_rejected(env):
    tenant, owner, warehouse, product = env
    partner = Partner.objects.create(
        tenant=tenant, name="عميل الافتتاح", partner_type="Customer")
    partner.refresh_from_db()
    assert partner.linked_account_id, "الطرف يُنشأ له حساب تلقائياً"
    opening = get_or_create_opening(tenant)
    with pytest.raises(DjangoValidationError) as exc:
        save_opening_lines(
            opening,
            start_date=START_DATE,
            account_lines=[{'account': partner.linked_account,
                            'debit': D('100'), 'credit': D('0')}],
        )
    message = str(exc.value)
    assert 'عميل الافتتاح' in message
    assert 'تبويب «الأطراف»' in message


def test_forbidden_account_rejected_at_post_time_too(env):
    """الحارس يعمل عند الترحيل أيضاً — بندٌ صار ممنوعاً بعد حفظه لا يمرّ."""
    tenant, owner, warehouse, product = env
    spare = Account.objects.create(
        tenant=tenant, code='1180', name='حساب مؤقت',
        account_type='Asset', is_active=True)
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=START_DATE,
        account_lines=[
            {'account': spare, 'debit': D('100'), 'credit': D('0')},
            {'account': _acc(tenant, '2102'), 'debit': D('0'), 'credit': D('100')},
        ],
    )
    # ربطه بطرف بعد الحفظ (نفس ما يفعله ربط الحساب من بطاقة الطرف)
    Partner.objects.create(
        tenant=tenant, name="مورد متأخر", partner_type="Supplier",
        linked_account=spare)

    with pytest.raises(DjangoValidationError) as exc:
        post_opening_balance(opening, user=owner)
    assert 'مورد متأخر' in str(exc.value)
    assert not JournalHeader.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE).exists()


# ── (ز) فترة مالية غائبة/مغلقة ⇒ خطأ قابل للفعل بلا حالة جزئية ───────────
def test_missing_fiscal_period_fails_with_no_partial_state(env):
    tenant, owner, warehouse, product = env
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=datetime.date(2021, 4, 1),  # لا فترات مالية لعام 2021
        account_lines=[
            {'account': _acc(tenant, '1101'), 'debit': D('500'), 'credit': D('0')},
        ],
        stock_lines=[
            {'product': product, 'warehouse': warehouse,
             'quantity': D('5'), 'unit_cost': D('20')},
        ],
    )

    with pytest.raises(DjangoValidationError) as exc:
        post_opening_balance(opening, user=owner)
    message = str(exc.value)
    assert 'فترة مالية' in message
    assert '2021-03-31' in message  # التاريخ المطلوب مذكور صراحةً

    opening.refresh_from_db()
    assert opening.status == OpeningBalance.STATUS_DRAFT
    assert not JournalHeader.objects.filter(
        tenant=tenant, reference_type=OPENING_REFERENCE_TYPE).exists()
    assert not StockMovement.objects.filter(tenant=tenant).exists()
    product.refresh_from_db()
    assert product.quantity_on_hand == D('0.0000')


def test_closed_fiscal_period_fails_with_no_stock_movement_left(env):
    """فترة مغلقة عند تاريخ القيد — الرسالة تدلّ على شاشة الفترات ولا تُخلَّف حركة."""
    from accounting.models import FiscalPeriod

    tenant, owner, warehouse, product = env
    FiscalPeriod.objects.filter(
        tenant=tenant, start_date__lte=ENTRY_DATE, end_date__gte=ENTRY_DATE,
    ).update(status='Closed', is_closed=True)
    opening = _fill_draft(tenant, warehouse, product)

    with pytest.raises(DjangoValidationError) as exc:
        post_opening_balance(opening, user=owner)
    assert 'مغلقة' in str(exc.value)
    assert not StockMovement.objects.filter(tenant=tenant).exists()
    product.refresh_from_db()
    assert product.quantity_on_hand == D('0.0000')


# ── (ح) عزل الشركات ──────────────────────────────────────────────────────
def test_tenant_isolation_between_two_companies(env):
    tenant_a, owner_a, warehouse_a, product_a = env
    tenant_b, owner_b, warehouse_b, product_b = _company("شركة ثانية", "opening_b")

    opening_a = _fill_draft(tenant_a, warehouse_a, product_a)
    post_opening_balance(opening_a, user=owner_a)

    summary_b = opening_balance_summary(tenant_b)
    assert summary_b['status'] == OpeningBalance.STATUS_DRAFT
    assert summary_b['account_lines'] == []
    assert summary_b['stock_lines'] == []
    assert summary_b['totals']['equity_plug'] == D('0.00')
    assert summary_b['id'] != opening_a.id

    # ترحيل الشركة (ب) لا يمنعه قيد الشركة (أ) ولا يمسّه
    opening_b = _fill_draft(tenant_b, warehouse_b, product_b, cash="700", loan="100",
                            qty="2", unit_cost="50")
    post_opening_balance(opening_b, user=owner_b)

    assert JournalHeader.objects.filter(
        tenant=tenant_a, reference_type=OPENING_REFERENCE_TYPE).count() == 1
    assert JournalHeader.objects.filter(
        tenant=tenant_b, reference_type=OPENING_REFERENCE_TYPE).count() == 1
    product_a.refresh_from_db()
    assert product_a.quantity_on_hand == D('10.0000')
    assert not JournalLine.objects.filter(
        journal__tenant=tenant_b, account__tenant=tenant_a).exists()


# ── ملخّص الأطراف + مسار الـAPI ──────────────────────────────────────────
def test_summary_reports_partner_opening_posted_state(env):
    tenant, owner, warehouse, product = env
    posted = Partner.objects.create(
        tenant=tenant, name="عميل مرحّل", partner_type="Customer",
        opening_balance=D('400'), opening_balance_date=ENTRY_DATE)
    pending = Partner.objects.create(
        tenant=tenant, name="عميل غير مرحّل", partner_type="Customer",
        opening_balance=D('250'), opening_balance_date=datetime.date(2021, 5, 5))

    rows = {r['id']: r for r in opening_balance_summary(tenant)['partners']}
    assert set(rows) == {posted.id, pending.id}
    assert rows[posted.id]['is_posted'] is True
    assert rows[posted.id]['journal'] is not None
    # تاريخ خارج أي فترة مالية ⇒ لم يُرحَّل قيده (والحفظ لم يسقط)
    assert rows[pending.id]['is_posted'] is False
    assert rows[pending.id]['journal'] is None
    assert rows[posted.id]['opening_balance'] == D('400.00')


def test_api_round_trip_save_post_unpost(env):
    tenant, owner, warehouse, product = env
    client = APIClient()
    client.force_authenticate(user=owner)
    headers = {'HTTP_X_TENANT_ID': str(tenant.TenantID)}

    saved = client.put(
        '/api/accounting/opening-balance/lines/',
        {
            'start_date': START_DATE.isoformat(),
            'account_lines': [
                {'account': _acc(tenant, '1101').id, 'debit': '5000', 'credit': '0'},
                {'account': _acc(tenant, '2102').id, 'debit': '0', 'credit': '2000'},
            ],
            'stock_lines': [
                {'product': product.id, 'warehouse': warehouse.id,
                 'quantity': '10', 'unit_cost': '30'},
            ],
        },
        format='json', **headers,
    )
    assert saved.status_code == 200, saved.data
    assert saved.data['entry_date'] == ENTRY_DATE.isoformat()
    # المال نصّ في الحمولة — لا عائم (مُرمِّز DRF يحوّل Decimal إلى float)
    assert saved.data['totals']['equity_plug'] == '3300.00'
    assert len(saved.data['account_lines']) == 2
    assert saved.data['stock_lines'][0]['value'] == '300.00'

    posted = client.post('/api/accounting/opening-balance/post/', {},
                         format='json', **headers)
    assert posted.status_code == 200, posted.data
    assert posted.data['status'] == OpeningBalance.STATUS_POSTED
    assert posted.data['journal'] is not None

    read = client.get('/api/accounting/opening-balance/', **headers)
    assert read.status_code == 200
    assert read.data['status'] == OpeningBalance.STATUS_POSTED

    # تعديل مسودة مستند مرحّل مرفوض برسالة تقول ما يجب فعله
    blocked = client.put(
        '/api/accounting/opening-balance/lines/',
        {'account_lines': []}, format='json', **headers,
    )
    assert blocked.status_code == 400
    assert 'ألغِ ترحيله' in str(blocked.data['error'])

    unposted = client.post('/api/accounting/opening-balance/unpost/', {},
                           format='json', **headers)
    assert unposted.status_code == 200, unposted.data
    assert unposted.data['status'] == OpeningBalance.STATUS_DRAFT
    product.refresh_from_db()
    assert product.quantity_on_hand == D('0.0000')


def test_api_does_not_leak_another_company_opening(env):
    tenant_a, owner_a, warehouse_a, product_a = env
    tenant_b, owner_b, warehouse_b, product_b = _company("شركة ثالثة", "opening_c")
    opening_a = _fill_draft(tenant_a, warehouse_a, product_a)
    post_opening_balance(opening_a, user=owner_a)

    client = APIClient()
    client.force_authenticate(user=owner_b)
    read = client.get('/api/accounting/opening-balance/',
                      HTTP_X_TENANT_ID=str(tenant_b.TenantID))
    assert read.status_code == 200
    assert read.data['id'] != opening_a.id
    assert read.data['status'] == OpeningBalance.STATUS_DRAFT
    assert read.data['account_lines'] == []

    # وحساب من الشركة (أ) لا يُقبل في بنود الشركة (ب)
    rejected = client.put(
        '/api/accounting/opening-balance/lines/',
        {
            'start_date': START_DATE.isoformat(),
            'account_lines': [
                {'account': _acc(tenant_a, '1101').id, 'debit': '100', 'credit': '0'},
            ],
        },
        format='json', HTTP_X_TENANT_ID=str(tenant_b.TenantID),
    )
    assert rejected.status_code == 400
    assert get_or_create_opening(tenant_b).account_lines.count() == 0


def test_zero_amount_lines_are_dropped_and_empty_post_refused(env):
    tenant, owner, warehouse, product = env
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=START_DATE,
        account_lines=[
            {'account': _acc(tenant, '1101'), 'debit': D('0'), 'credit': D('0')},
        ],
        stock_lines=[],
    )
    assert opening.account_lines.count() == 0
    with pytest.raises(DjangoValidationError) as exc:
        post_opening_balance(opening, user=owner)
    assert 'بنداً واحداً على الأقل' in str(exc.value)


def test_account_line_rejects_both_sides_at_once(env):
    tenant, owner, warehouse, product = env
    opening = get_or_create_opening(tenant)
    with pytest.raises(DjangoValidationError) as exc:
        save_opening_lines(
            opening,
            start_date=START_DATE,
            account_lines=[{'account': _acc(tenant, '1101'),
                            'debit': D('10'), 'credit': D('5')}],
        )
    assert 'لا الطرفين معاً' in str(exc.value)


# ── (ط) رِجل الأطراف: عكس قيد طرف واحد، والمبلغ المرحّل في الملخص (T119-2) ──

def _partner(tenant, name, amount, partner_type='Customer'):
    partner = Partner.objects.create(
        tenant=tenant, name=name, partner_type=partner_type,
        opening_balance=D(amount), opening_balance_date=ENTRY_DATE,
    )
    partner.refresh_from_db()
    return partner


def _partner_journals(tenant, partner):
    return JournalHeader.objects.filter(
        tenant=tenant, reference_type='PARTNER_OPENING', reference_id=partner.id)


def test_partner_reverse_endpoint_deletes_journal_and_resave_reposts(env):
    """«لا تعديل لرصيد مرحّل إلا بعكسه صراحةً»: العكس يحذف القيد، ثم إعادة
    الحفظ ترحّل المبلغ الجديد."""
    tenant, owner, warehouse, product = env
    partner = _partner(tenant, "عميل الافتتاح", "500")
    assert _partner_journals(tenant, partner).count() == 1

    client = APIClient()
    client.force_authenticate(user=owner)
    resp = client.post(
        f'/api/accounting/opening-balance/partners/{partner.id}/reverse/',
        {}, format='json', HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert resp.status_code == 200, resp.data
    assert not _partner_journals(tenant, partner).exists()
    row = next(r for r in resp.data['partners'] if r['id'] == partner.id)
    assert row['is_posted'] is False
    assert row['journal'] is None

    partner.opening_balance = D("800")
    partner.save()
    header = _partner_journals(tenant, partner).get()
    assert header.lines.filter(
        account=partner.linked_account, debit=D("800.00")).exists()


def test_partner_reverse_endpoint_refuses_unposted_and_other_tenant(env):
    tenant, owner, warehouse, product = env
    tenant_b, owner_b, _, _ = _company("شركة أخرى", "opening_other")
    partner_b = _partner(tenant_b, "عميل الشركة الأخرى", "400")

    client = APIClient()
    client.force_authenticate(user=owner)

    # طرف بلا قيد مرحّل ⇒ رفض واضح لا نجاح صامت
    unposted = _partner(tenant, "عميل بلا رصيد", "0")
    refused = client.post(
        f'/api/accounting/opening-balance/partners/{unposted.id}/reverse/',
        {}, format='json', HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert refused.status_code == 400, refused.data

    # طرف شركة أخرى لا يُعكس من هذه الشركة — وقيده باقٍ كما هو
    leaked = client.post(
        f'/api/accounting/opening-balance/partners/{partner_b.id}/reverse/',
        {}, format='json', HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert leaked.status_code == 400, leaked.data
    assert _partner_journals(tenant_b, partner_b).count() == 1


def test_editing_posted_partner_balance_changes_nothing_and_summary_shows_posted(env):
    """تعديل رصيد مرحّل بلا عكس لا يغيّر القيد — والملخص يقول المبلغ المرحّل
    فعلاً بجانب المُدخل، فلا يظنّ المستخدم أن رقمه الجديد صار في الدفاتر."""
    tenant, owner, warehouse, product = env
    partner = _partner(tenant, "عميل مرحّل", "500")
    supplier = _partner(tenant, "مورد مقدَّم", "-300", partner_type='Supplier')

    partner.opening_balance = D("900")
    partner.save()

    journals = _partner_journals(tenant, partner)
    assert journals.count() == 1
    assert journals.get().lines.filter(
        account=partner.linked_account, debit=D("500.00")).exists()

    summary = opening_balance_summary(tenant)
    row = next(r for r in summary['partners'] if r['id'] == partner.id)
    assert row['is_posted'] is True
    assert row['opening_balance'] == D("900.00")
    assert row['posted_amount'] == D("500.00")

    srow = next(r for r in summary['partners'] if r['id'] == supplier.id)
    assert srow['posted_amount'] == D("-300.00")


# ── (ي) أصناف الافتتاح المتتبَّعة تسلسلياً: المُسجَّل مقابل المطلوب (T119-5) ──
#
# الافتتاح يُنشئ كميةً في المخزن ولا يُنشئ وحدةً مُرقَّمة واحدة، وشركةٌ نمط بيعها
# «إجباري» تُمنع من بيع بضاعة افتتاحها عند `apply_sales_serials`. الملخّص هو ما
# يقول النقص ويصل بالمستخدم إلى مسار الترقيم القائم.

def _serialized_product(tenant, sku, name):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=name,
        quantity_on_hand=D('0'), avg_cost=D('0'), is_serialized=True,
    )


def test_summary_reports_serialized_items_registered_vs_required(env):
    """صنف متتبَّع في افتتاحٍ مرحّل يُذكر بنقصه، وغير المتتبَّع لا يُذكر أصلاً."""
    from inventory.models import ProductSerial
    from inventory.serials import register_existing_serials

    tenant, owner, warehouse, product = env
    tracked = _serialized_product(tenant, "OB-SER", "حاسوب مُرقَّم")
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=START_DATE,
        account_lines=[
            {'account': _acc(tenant, '1101'), 'debit': D('5000'), 'credit': D('0')},
        ],
        stock_lines=[
            {'product': tracked, 'warehouse': warehouse,
             'quantity': D('3'), 'unit_cost': D('1200')},
            {'product': product, 'warehouse': warehouse,
             'quantity': D('10'), 'unit_cost': D('30')},
        ],
    )
    post_opening_balance(opening, user=owner)

    rows = opening_balance_summary(tenant)['serial_items']
    assert [r['product'] for r in rows] == [tracked.id]
    assert rows[0]['product_name'] == "حاسوب مُرقَّم"
    assert rows[0]['product_sku'] == "OB-SER"
    assert rows[0]['quantity'] == 3
    assert rows[0]['serials_registered'] == 0
    # سبب وجود الصفّ: الترحيل لم يُنشئ وحدةً واحدة
    assert not ProductSerial.objects.filter(tenant=tenant, product=tracked).exists()

    # الترقيم من المسار القائم نفسه — سقفه رصيد المخزن الذي أنشأه الافتتاح
    tracked.refresh_from_db()
    register_existing_serials(
        tenant_id=tenant.TenantID, product=tracked,
        serials=['SN-0001', 'SN-0002', 'SN-0003'],
    )
    row = opening_balance_summary(tenant)['serial_items'][0]
    assert row['serials_registered'] == row['quantity'] == 3


def test_serial_counts_are_per_product_and_survive_a_sale(env):
    """صنف في مستودعين صفٌّ واحد بمجموع كميته (`ProductSerial` بلا مستودع)،
    ووحدةٌ بيعت تبقى «مُسجَّلة» — وإلا عاد الصنف ناقص الترقيم بعد إتمامه."""
    from inventory.models import ProductSerial
    from inventory.serials import register_existing_serials

    tenant, owner, warehouse, product = env
    other = Warehouse.objects.create(tenant=tenant, name="مستودع ثانٍ")
    tracked = _serialized_product(tenant, "OB-SER2", "طابعة مُرقَّمة")
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=START_DATE,
        stock_lines=[
            {'product': tracked, 'warehouse': warehouse,
             'quantity': D('2'), 'unit_cost': D('500')},
            {'product': tracked, 'warehouse': other,
             'quantity': D('1'), 'unit_cost': D('500')},
        ],
    )
    post_opening_balance(opening, user=owner)

    rows = opening_balance_summary(tenant)['serial_items']
    assert len(rows) == 1
    assert rows[0]['quantity'] == 3

    tracked.refresh_from_db()
    register_existing_serials(
        tenant_id=tenant.TenantID, product=tracked,
        serials=['PR-1', 'PR-2', 'PR-3'],
    )
    ProductSerial.objects.filter(tenant=tenant, product=tracked, serial='PR-1').update(
        status=ProductSerial.STATUS_SOLD)
    row = opening_balance_summary(tenant)['serial_items'][0]
    assert row['serials_registered'] == 3


def test_serial_counts_do_not_leak_between_companies(env):
    """عدُّ الوحدات مفلترٌ بالشركة — العدد تسريبٌ أيضاً."""
    from inventory.serials import register_existing_serials

    tenant_a, owner_a, warehouse_a, _ = env
    tenant_b, owner_b, warehouse_b, _ = _company("شركة الأرقام", "opening_serials_b")

    tracked_a = _serialized_product(tenant_a, "OB-SER-A", "صنف الشركة أ")
    tracked_b = _serialized_product(tenant_b, "OB-SER-B", "صنف الشركة ب")
    for tenant, warehouse, tracked, owner in (
        (tenant_a, warehouse_a, tracked_a, owner_a),
        (tenant_b, warehouse_b, tracked_b, owner_b),
    ):
        opening = get_or_create_opening(tenant)
        save_opening_lines(
            opening,
            start_date=START_DATE,
            stock_lines=[{'product': tracked, 'warehouse': warehouse,
                          'quantity': D('2'), 'unit_cost': D('100')}],
        )
        post_opening_balance(opening, user=owner)

    tracked_b.refresh_from_db()
    register_existing_serials(
        tenant_id=tenant_b.TenantID, product=tracked_b, serials=['B-1', 'B-2'],
    )

    rows_a = opening_balance_summary(tenant_a)['serial_items']
    assert [r['product'] for r in rows_a] == [tracked_a.id]
    assert rows_a[0]['serials_registered'] == 0
    rows_b = opening_balance_summary(tenant_b)['serial_items']
    assert rows_b[0]['serials_registered'] == 2


def test_api_payload_carries_serial_items_as_integers(env):
    """الحمولة: الأعداد أعدادٌ صحيحة (لا مال هنا) والمبالغ تبقى نصوصاً."""
    tenant, owner, warehouse, product = env
    tracked = _serialized_product(tenant, "OB-SER-API", "هاتف مُرقَّم")
    opening = get_or_create_opening(tenant)
    save_opening_lines(
        opening,
        start_date=START_DATE,
        stock_lines=[{'product': tracked, 'warehouse': warehouse,
                      'quantity': D('4'), 'unit_cost': D('800')}],
    )
    post_opening_balance(opening, user=owner)

    client = APIClient()
    client.force_authenticate(user=owner)
    read = client.get('/api/accounting/opening-balance/',
                      HTTP_X_TENANT_ID=str(tenant.TenantID))
    assert read.status_code == 200
    row = read.data['serial_items'][0]
    assert row == {
        'product': tracked.id, 'product_sku': 'OB-SER-API',
        'product_name': 'هاتف مُرقَّم', 'quantity': 4, 'serials_registered': 0,
    }
    assert read.data['totals']['stock_value'] == '3200.00'
