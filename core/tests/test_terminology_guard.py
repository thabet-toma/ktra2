"""ISSUE #82 — حارس المعجم: يمنع عودة مصطلحٍ مقنَّن نصّاً حرفياً في أي ملف إنتاج.

**مراجعة 2026-09-03:** النسخة الأولى راقبت خمسة ملفاتٍ رُحِّلت يدوياً فقط —
فملفٌّ جديد (أو أيٌّ من الباقين) يكتب «فاتورة مبيعات» حرفياً كان يمرّ بلا أن
يلاحظ الحارس، وهذا بالضبط كيف تراكمت الثمانية والثلاثون موضعاً التي فتحت
هذه التذكرة. الحارس الآن يمشي على **شجرة الإنتاج كلّها**.

**العبارات المراقَبة مُشتقّة لا مكتوبة يدوياً:** `_watched_phrases()` تقرأ
`core.terminology` نفسها وتُبقي العبارات **المركّبة** (كلمتان فأكثر) **التي
تحمل تجاوزاً فعلياً بين قالبٍ وآخر** — أي التي حرفيّتها خطأٌ وظيفي محتمل
(نصٌّ يتجاهل قالب الشركة)، لا كل اسم مستند. اليوم هذا يساوي {"فاتورة مبيعات",
"فاتورة أتعاب"} (`doc.sales_invoice`). بقية أنواع المستند (`سند قبض`، `عرض
سعر`، …) قيمتها واحدة في كل قالب — كتابتها حرفياً أسلوب كودٍ لا خطأً وظيفياً،
فحراستها مسحاً شاملاً توسيعٌ منفصل خارج نطاق هذه التذكرة.

**الكلمات المفردة (`منتج`/`خدمة`) مستثناة عمداً**: كلمتان عاديتان تتكرران في
سياقاتٍ لا علاقة لها بالمعجم («خدمة ما بعد البيع» في `Sidebar.tsx` مثال حيّ)
— مسحهما شاملاً يُغرق في إنذارات كاذبة.

**البنية:**
1. مسحٌ شامل لـ`.py`/`.ts`/`.tsx` تحت جذر المستودع، مستثنياً `tests/`،
   `*.test.*`، `e2e/`، `migrations/`، `docs/` (وأدلّة الأدوات: `node_modules`،
   `dist`، `build`، `.git`، `venv`).
2. أي تطابق خارج `ALLOWLIST` يُسقط الحارس أحمر.
3. `ALLOWLIST` صريحة، **بسببٍ مكتوب لكل مدخل** — الدَّين ظاهرٌ ومعدود بدل أن
   يختفي خلف نطاق مراقبةٍ ضيّق. يشمل ما استثنته التذكرة نصّاً (`core/activity.py`
   — أوصاف سجلّ نشاط تاريخية) و`TenantBook.DOCUMENT_TYPES`/`terms.ts` بصفتهما
   **مصدر** المعجم لا نسخة عنه.
4. `WATCHED_TERM_CALLS` تحقّقٌ إيجابي: الملفات المُرحَّلة فعلياً لـ`term()`
   يجب أن تبقى تستدعيه — حذف الاستدعاء (لا استبداله بحرفي) يمرّ صامتاً من
   الفحص الأول وحده.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

from core.terminology import TEMPLATE_TERM_OVERRIDES, _default_terms

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PRODUCTION_EXTENSIONS = (".py", ".ts", ".tsx")

#: أدلّة تُستثنى كاملةً من المسح — بالاسم لا بالمسار الكامل، فتُلتقط أينما
#: ظهرت (`sales/tests/`، `frontend_v2/e2e/`، `logistics/migrations/`، …).
EXCLUDED_DIR_RE = re.compile(
    r"(^|/)(tests?|e2e|migrations|docs|node_modules|dist|build|\.git|venv|\.venv|\.claude)(/|$)"
)
#: ملفات اختبار مفردة خارج مجلد tests/ (نادرة هنا لكن الحارس يحترم الاتفاقية).
EXCLUDED_FILE_RE = re.compile(r"(^|/)test_[^/]+\.py$|\.test\.tsx?$")


def _watched_phrases() -> set[str]:
    """عباراتٌ مركّبة (كلمتان فأكثر) من مفاتيح تحمل تجاوزاً فعلياً بالقالب."""
    defaults = _default_terms()
    keys_with_overrides = {
        key for overrides in TEMPLATE_TERM_OVERRIDES.values() for key in overrides
    }
    values = set()
    for key in keys_with_overrides:
        if key in defaults:
            values.add(defaults[key])
        for overrides in TEMPLATE_TERM_OVERRIDES.values():
            if key in overrides:
                values.add(overrides[key])
    return {v for v in values if v and len(v.split()) >= 2}


# ── قائمة السماح — كل مدخلٍ بسببه ─────────────────────────────────────────
ALLOWLIST: dict[str, str] = {
    # مصدر المعجم نفسه — القيمة تُعرَّف هنا حرفياً لا نسخة عنها.
    "core/terminology.py":
        "تعريف المعجم نفسه (DEFAULT_TERMS/TEMPLATE_TERM_OVERRIDES) — مصدرٌ لا نسخة.",
    "frontend_v2/utils/terms.ts":
        "تعريف المعجم على الواجهة (احتياطي أول رسمة قبل ردّ الخادم) — مصدرٌ لا نسخة.",
    "tenants/models.py":
        "مصدر المعجم — TenantBook.DOCUMENT_TYPES التي يُشتقّ منها core.terminology._default_terms.",
    "tenants/company_templates.py": "تعليق توثيقي فقط، لا نصّ يُنفَّذ.",
    # مستثناة بنصّ التذكرة — أوصاف سجلّ نشاط تاريخية، حقيقةٌ يُفهرَس نصّها بالبحث.
    "core/activity.py": "مستثناة بنصّ التذكرة — وصف سجلّ نشاط مخزَّن.",
    "accounting/serializers.py": "تعليق T-COAMENU فقط، لا نصّ يُنفَّذ — النصّ الفعلي (SOURCE_LABEL_MAP وbuild_journal_reference_summary) مُرحَّل لـterm().",
    "sales/views.py":
        "أوصاف log_activity المتبقّية — نفس فئة استثناء core/activity.py. "
        "الموضع الفعلي المرئي للمستخدم (document_label في unpost_document) رُحِّل لـterm().",
    # تعليقات/توثيق داخلي — لا نصّ يصل المستخدم.
    "sales/services/calc.py": "تعليق داخلي فقط.",
    "sales/services/foundation.py": "تعليق داخلي فقط.",
    "sales/agent_api.py": "docstring توثيق مطوّر لنقطة /api/agent، لا نص واجهة.",
    "frontend_v2/App.tsx": "تعليقان توثيقيان فقط، لا نصّ يُعرض.",
    "frontend_v2/utils/officeShell.ts": "تعليق فقط.",
    "frontend_v2/components/sales/DeliverGoodsModal.tsx": "تعليق رأس الملف فقط.",
    "frontend_v2/components/sales/CustomerQuickAddModal.tsx": "تعليق JSDoc فقط.",
    "frontend_v2/components/sales/SalesInvoicesPage.tsx": "تعليقٌ يشير لقرار #53 فقط.",
    "frontend_v2/components/partners/StatementDetailsModal.tsx": "تعليق JSX فقط.",
    "frontend_v2/components/office/ClientBooksPanel.tsx": "تعليق فقط.",
    "frontend_v2/components/sales/SalesInvoiceEditor.tsx":
        "تعليقان فقط (قرار #53 سابق، وتوثيق شرط حساب) — كل نصّ مُنفَّذ في هذا "
        "الملف مُرحَّل فعلاً لـterm() (يحرسه WATCHED_TERM_CALLS أدناه).",
    # قرارات تصميم واجهة مقصودة — راجعتها المراجعة وأقرّتها.
    "frontend_v2/utils/partnerActions.ts":
        "زرّان متجاوران في قائمة العميل: «فاتورة مبيعات» و«فاتورة أتعاب» "
        "(قرار #53) مختلفان فعلاً لا مترادفان — ترجمة الأول تُنتج تكراراً "
        "بصرياً في مكتب المحاسبة؛ قرار واجهة خارج نطاق #82.",
    "frontend_v2/utils/entityLinks.ts":
        "referenceTypeLabel() دالّة صرفة بلا React hook تخدم عدّة مستدعين "
        "(كشف الحساب، شاشات الشركاء)؛ تمرير term() يتطلب تغيير توقيعها وكل "
        "مستدعياتها — خارج نطاق #82 (مُقَرّ في المراجعة).",
    "frontend_v2/components/activity/activityMeta.tsx":
        "entityLabel() دالّة صرفة بثلاثة مستدعين (ActivityLogPage، "
        "PlatformCompanyPanel، EntityActivityLog)؛ نفس علّة entityLinks.ts "
        "أعلاه — خارج نطاق #82 (مُقَرّ في المراجعة).",
}


def _iter_production_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in PRODUCTION_EXTENSIONS:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if EXCLUDED_DIR_RE.search(rel) or EXCLUDED_FILE_RE.search(rel):
            continue
        yield rel, path


# ── الملفات المُرحَّلة فعلياً — تحقّقٌ إيجابي: كلّ عبارة استدعاءٍ يجب أن تبقى ──
WATCHED_TERM_CALLS: dict[str, list[str]] = {
    "accounting/serializers.py": ["tenant_term("],
    "accounting/services.py": ["tenant_term(cheque.tenant"],
    "sales/views.py": ["tenant_term(invoice.tenant"],
    "frontend_v2/components/settings/GroupConstantsPage.tsx": ["term(`doc."],
    "frontend_v2/components/sales/SalesInvoicePrintView.tsx": ["term('doc.sales_invoice')"],
    "frontend_v2/components/partners/PartnerProfilePage.tsx": ["term('doc.sales_invoice')"],
    "frontend_v2/components/sales/SalesInvoiceEditor.tsx": [
        'term("line.item")', 'term("doc.sales_invoice")',
    ],
    "frontend_v2/components/accounting/AccountingJournalListPage.tsx": [
        'term("doc.sales_invoice")',
    ],
    "frontend_v2/components/layout/quickActions.tsx": ["salesInvoiceLabel"],
    "frontend_v2/components/layout/GlobalActionBar.tsx": ['term("doc.sales_invoice")'],
    "frontend_v2/components/layout/GlobalContextMenu.tsx": ['term("doc.sales_invoice")'],
    "frontend_v2/components/kit/KitStory.tsx": ['term("doc.sales_invoice")'],
}


class TerminologyGuardTest(SimpleTestCase):
    """كل إخفاق هنا يعني: عبارةً من المعجم عادت نصّاً حرفياً خارج قائمة السماح."""

    def test_no_hardcoded_compound_terms_outside_allowlist(self):
        phrases = _watched_phrases()
        self.assertTrue(phrases, "لا عبارات مركّبة محروسة — تحقّق من core.terminology")
        offenders = []
        for rel, path in _iter_production_files():
            if rel in ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for phrase in phrases:
                if phrase in text:
                    offenders.append(f"{rel} → «{phrase}»")
        self.assertEqual(
            offenders, [],
            "عبارات معجم عادت نصّاً حرفياً خارج ALLOWLIST — استعمل term()/"
            "term(tenant, key)، أو أضِف الملف إلى ALLOWLIST بسببٍ مكتوب:\n  "
            + "\n  ".join(offenders),
        )

    def test_watched_files_still_call_term(self):
        """الحارس السابق يمرّ صامتاً لو حُذف استدعاء `term()` نفسه — تحقّق إيجابي."""
        missing = []
        for rel, needles in WATCHED_TERM_CALLS.items():
            path = REPO_ROOT / rel
            self.assertTrue(path.exists(), f"ملف مراقَب غير موجود: {rel}")
            text = path.read_text(encoding="utf-8")
            for needle in needles:
                if needle not in text:
                    missing.append(f"{rel} (متوقَّع: {needle})")
        self.assertEqual(
            missing, [],
            "ملفات مراقَبة بلا استدعاء term() المتوقَّع — رُحِّلت ثم فُكَّت "
            "بصمت، أو غيّرت شكل الاستدعاء دون تحديث WATCHED_TERM_CALLS:\n  "
            + "\n  ".join(missing),
        )

    def test_allowlist_entries_point_to_real_files(self):
        """مدخلٌ لملفٍ محذوف = قائمة سماح تتعفّن هي الأخرى."""
        missing = [rel for rel in ALLOWLIST if not (REPO_ROOT / rel).exists()]
        self.assertEqual(missing, [], f"مداخل ALLOWLIST لملفات غير موجودة: {missing}")

    def test_allowlist_entries_are_still_needed(self):
        """مدخلٌ لا يحمل عبارةً محروسة بعد الآن = دَينٌ سُدِّد ولم يُشطَب."""
        phrases = _watched_phrases()
        stale = []
        for rel in ALLOWLIST:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
            if not any(phrase in text for phrase in phrases):
                stale.append(rel)
        self.assertEqual(
            stale, [],
            "مداخل ALLOWLIST لم تعد تحمل أي عبارة محروسة — احذفها كي تبقى "
            "القائمة الدَّين الحقيقي لا أكثر:\n  " + "\n  ".join(stale),
        )
