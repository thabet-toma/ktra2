"""حزمة core.reports — المرحلة 3: تفكيك reports.py (2,350 سطراً).
_framework يحمل السجل (REPORTS/register) وأدوات العرض المشتركة؛ كل وحدة
دومين تحمل تقاريرها ونداءات register() التي تُنفَّذ عند استيرادها هنا —
فيمتلئ REPORTS المشترك. صفر تغيير سلوك (تحقّق byte-for-byte).
"""
from ._framework import *  # noqa: F401,F403
from ._framework import (  # الأدوات ذات الشرطة السفلية لا يجلبها *
    DEC,
    ZERO,
    CATEGORIES,
    KIND_MONEY,
    KIND_NUMBER,
    KIND_INT,
    KIND_DATE,
    KIND_TEXT,
    ReportColumn,
    ReportFilter,
    ReportSpec,
    REPORTS,
    register,
    DATE_FILTERS,
    _parse_date,
    _date_range,
    _apply_dates,
    _int_param,
    _money,
    _qty,
    _sum,
    _money_sum,
    compute_totals,
    report_catalog,
    MAX_ROWS,
    run_report,
)

# استيراد وحدات الدومين ينفّذ نداءات register() فيمتلئ REPORTS.
from . import sales  # noqa: F401
from . import purchases  # noqa: F401
from . import financial  # noqa: F401
from . import inventory  # noqa: F401
from . import treasury  # noqa: F401
from . import ledger_import  # noqa: F401
from . import procurement_logistics  # noqa: F401
from . import hr  # noqa: F401
from . import after_sales  # noqa: F401

__all__ = ["REPORTS", "register", "report_catalog", "run_report",
           "ReportSpec", "ReportColumn", "ReportFilter", "compute_totals"]
