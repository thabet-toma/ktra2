"""حرّاس السجلّ — ما يُسقِط توسيعاً خاطئاً قبل أن يصل إلى الإنتاج.

هذه ليست اختبارات سلوك بل اختبارات **بنية**: كل واحد منها يحرس انحرافاً لا
يُنتج استثناءً ولا صفحةً مكسورة، بل يمرّ صامتاً حتى يُكتشف على قاعدة الإنتاج.
"""
import pytest

from docshare.documents import DOC_TYPES
from docshare.models import DOC_TYPE_CHOICES, DOC_TYPE_MAX_LENGTH, DocumentShare


def test_choices_match_the_registry():
    """قائمتان لحقيقةٍ واحدة — والانحراف بينهما يُخرِس `get_doc_type_display`.

    `models.py` لا يقدر أن يستورد `documents.py` (يجرّ نماذج نصف المنصّة أثناء
    إقلاع التطبيقات)، فالثمن قائمةٌ ثانية — وهذا هو ثمنُها المدفوع هنا.
    """
    assert {key for key, _ in DOC_TYPE_CHOICES} == set(DOC_TYPES)
    for key, label in DOC_TYPE_CHOICES:
        assert label == DOC_TYPES[key]["label"], key


def test_doc_type_keys_fit_the_column():
    """أطول مفتاح ≤ طول العمود.

    العمود كان **٢٠** يوم كان النوعان مبيعاتٍ فقط. مفتاحٌ أطول من العمود لا
    يرمي على MySQL بل **يُلغي القيد بصمت**، وSQLite في هذه المجموعة لا يكشفه
    أبداً — فتمرّ الاختبارات خضراء على ميزةٍ لا تحفظ شيئاً. القياس هنا لا هناك.
    """
    column = DocumentShare._meta.get_field("doc_type").max_length
    assert column == DOC_TYPE_MAX_LENGTH
    longest = max(DOC_TYPES, key=len)
    assert len(longest) <= column, (
        f"المفتاح «{longest}» ({len(longest)} محرفاً) أطول من العمود ({column})"
    )


def test_every_type_declares_a_complete_spec():
    """مواصفةٌ ناقصة تنفجر وقت التشغيل على أول زائر، لا وقت التسجيل."""
    required = {"label", "loader", "builder", "permission", "audience", "decision"}
    for doc_type, spec in DOC_TYPES.items():
        assert required <= set(spec), f"{doc_type}: ينقصه {required - set(spec)}"
        assert callable(spec["loader"]), doc_type
        assert callable(spec["builder"]), doc_type
        assert spec["audience"] in ("customer", "supplier"), doc_type


def test_every_decision_spec_is_complete():
    """نوعٌ يقبل قراراً بمواصفةٍ ناقصة يرمي `KeyError` على الزائر لا علينا."""
    required = {
        "title", "hint", "accept_label", "reject_label",
        "settled_accepted", "settled_rejected", "expired_note",
        "is_open", "closed_reason", "apply", "entity_type", "entity_label",
    }
    for doc_type, spec in DOC_TYPES.items():
        decision = spec.get("decision")
        if decision is None:
            continue
        assert required <= set(decision), (
            f"{doc_type}: مواصفة القرار ينقصها {required - set(decision)}"
        )


@pytest.mark.parametrize("key", sorted(DOC_TYPES))
def test_permission_key_exists_in_the_catalog(key):
    """صلاحيةٌ باسمٍ مطبعيّ = `require_perm` يرفض الجميع أبداً، بلا رسالة تشرح."""
    from core.access import PERMISSIONS

    catalog = {perm["key"] for perm in PERMISSIONS}
    assert DOC_TYPES[key]["permission"] in catalog, DOC_TYPES[key]["permission"]
