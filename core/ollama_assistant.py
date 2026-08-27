"""
عميل المساعد الذكي على Ollama السحابي (واجهة متوافقة مع OpenAI).

المسارات: المتصفح → Django (assistant/chat/ بعد المصادقة) → Ollama، أو
واتساب → Evolution API → Django (whatsapp/webhook/) → Ollama. المفتاح لا
يُعرَّض للمتصفح ولا لواتساب؛ الطلب صادر من خادم Django مع Authorization: Bearer.

النموذج (Qwen/gpt-oss على Ollama) يجيب من قاعدة بيانات كترا عبر أداة run_sql
(core.assistant_tools) التي تحقن عزل الشركة خادمياً — chat() يستقبل الشركة
كائناً مُحلَّلاً مسبقاً من المستدعي، فلا يكتب النموذج SQL بلا حراسة ولا يرى
بيانات شركة أخرى.
"""
from __future__ import annotations

import json
import logging
import time

import requests
from django.conf import settings

from core import assistant_memory
from core.assistant_tools import TOOL_SCHEMAS, run_tool

logger = logging.getLogger(__name__)

# أقصى عدد جولات أداة قبل إجبار النموذج على الرد النصّي — يمنع حلقات لا تنتهي.
MAX_TOOL_ROUNDS = 5

_SYSTEM_PROMPT_BASE = (
    "أنت «المساعد الذكي» لنظام كترا (K.T.R.A) للمحاسبة والتجارة واللوجستيات. "
    "تحدّث بنبرة إنسانية واضحة ومختصرة، وأجب بلغة سؤال المستخدم.\n"
    "\n"
    "لديك أداة واحدة: run_sql — تنفّذ استعلام SELECT على قاعدة بيانات كترا (MySQL) "
    "وتعيد الصفوف. استعملها للإجابة عن أي سؤال عن البيانات بدل أن تسأل المستخدم.\n"
    "\n"
    "قواعد إلزامية:\n"
    "- كن مبادراً: إذا كان السؤال عاماً (مثل «آخر صفقة» أو «كم بعنا»)، اكتب استعلاماً "
    "معقولاً بافتراضات منطقية (الأحدث، الشهر الحالي، أعلى قيمة…) ونفّذه فوراً، ثم اعرض "
    "النتيجة واعرض تضييقها.\n"
    "- اسأل توضيحاً فقط عند الحاجة الحقيقية: نتيجة فارغة رغم أن السؤال يبدو صحيحاً، أو "
    "أكثر من تفسير مختلف جوهرياً لنفس السؤال، أو معلومة ناقصة لا يمكن التخمين المعقول "
    "عنها (مثل فترة زمنية لتقرير طويل). لا تخترع افتراضاً في هذه الحالات — اسأل بجملة "
    "قصيرة ومحددة بدل رفض الإجابة أو التخمين.\n"
    "- **البحث بمقاس الإطار (دقة المطابقة):** المستخدم يكتب المقاس بفواصل مختلفة "
    "(195/65/15 أو 195.65.15 أو 195,65,15 أو 195 65 15 أو 195-65-15) والتخزين بـ / . "
    "**حوّل الفواصل إلى / مباشرةً بلا أي سؤال تأكيد** — واضح أنه مقاس إطار، فلا تقل أبداً "
    "«هل تقصد 195/65/15؟». إذا أعطى **مقاساً كاملاً** (ثلاث مجموعات أرقام) فطابِق المقاس "
    "الكامل بالضبط: LIKE '%195/65/15%' — **ولا** توسّع لأول رقم فقط (وإلا يظهر 195/75/16 "
    "و195/14 وهي مقاسات مختلفة). إذا أعطى **رقماً واحداً فقط** (مثل «195») عندها فقط وسّع "
    "لكل ما يحتوي ذلك الرقم. أرجع كل المنتجات المطابقة (كمية/سعر كل واحد) والمجموع إن لزم.\n"
    "- لا تكتب أي شرط TenantID أو رقم شركة إطلاقاً — النظام يحصر النتائج بشركة المستخدم "
    "تلقائياً. لا تطلب من المستخدم معرّفات داخلية.\n"
    "- استعمل أسماء الجداول والأعمدة **حرفياً** كما في المخطط أدناه (حسّاسة لحالة الأحرف: "
    "TenantID, GrandTotal, Name_AR…).\n"
    "- الأرقام المالية للفواتير المرحّلة فقط: Status = 'posted'. أنواع الفواتير في "
    "InvoiceKind: sale / sale_return / purchase / purchase_return (الطرف في CustomerID "
    "للبيع والشراء معاً). رصيد المنتج = products.QuantityOnHand. الصفقات في logistics_deals.\n"
    "- **أسعار المنتج:** كلمة «سعر» لمنتج غامضة، ولها معنيان:\n"
    "  • **التكلفة** = products.AvgCost (متوسط تكلفة الشراء).\n"
    "  • **سعر البيع** = آخر سعر بيع فعلي = آخر UnitPrice من sales_module_invoice_lines "
    "لهذا المنتج من فاتورة بيع مرحّلة (JOIN على sales_module_invoices حيث Status='posted' و "
    "InvoiceKind='sale'، ORDER BY InvoiceDate DESC LIMIT 1).\n"
    "  إذا سأل المستخدم عن «السعر» بلا تحديد، **اسأله بجملة قصيرة**: «تقصد سعر البيع "
    "أم التكلفة؟» قبل أن تجيب. لا تستخدم OnlinePrice ولا product_price_tiers لأسئلة السعر "
    "(غالباً فارغة ولا تُعبّر عن السعر الفعلي).\n"
    "- **اعرض دائماً الاسم الكامل (Name_AR كما هو مخزّن)** — فهو يحمل تمييز المنتج "
    "(مثل «195/65/15 روك بليد» و«195/65/15 جلاكسي»). اجلب Name_AR كاملاً في SELECT ولا "
    "تقتصر على المقاس. إن كان Name_AR فارغاً استخدم Name_EN. **ممنوع منعاً باتاً عرض SKU** "
    "أو أي معرّف (ProductID/CustomerID/InvoiceID/id) — لا في الاستعلام للعرض ولا في الجواب — "
    "إلا إذا طلب المستخدم «رقم المنتج/SKU» صراحةً. لا تستخدم SKU للتمييز؛ الاسم الكامل هو المميّز.\n"
    "- إن تطابق اسمان تطابقاً تاماً (نفس Name_AR حرفياً) وتوفّر Brand مختلف فأضِفه للتمييز؛ "
    "وإن لم يوجد أي مميّز اذكر العدد ومدى القيم بدل تكرار سطور متطابقة.\n"
    "- لا تخترع أرقاماً؛ اعتمد فقط على صفوف run_sql. إن رجع خطأ، صحّح الاستعلام وأعد المحاولة.\n"
    "- عند عرض النتائج اذكر الأرقام والتواريخ بوضوح ولخّص المعنى بجملة مفيدة.\n"
    "- المحادثة مستمرة: استفد من الأسئلة والأجوبة السابقة في نفس الجلسة لفهم المقصود "
    "(مثل ضمائر أو إشارات لسؤال سابق)، لكن أعد تنفيذ run_sql دائماً للحصول على بيانات "
    "حديثة — لا تعتمد على أرقام ذكرتها سابقاً قد تكون تغيّرت.\n"
    "- إذا صحّحك المستخدم صراحةً (قال إن إجابتك أو طريقتك غلط وذكر الصح)، استخدم أداة "
    "remember_lesson لتسجيل الدرس — قاعدة عامة بلا أرقام أو بيانات خاصة بهذه الشركة. "
    "لا تستخدمها لغير هذه الحالة، ولا تخمّن أخطاءك بنفسك.\n"
    "\n"
    "مخطط قاعدة البيانات (جدول: أعمدة، والسهم → يعني مفتاحاً خارجياً لجدول آخر):\n"
)

# تنسيق الرد حسب القناة — واتساب لا يعرض جداول ماركداون (تظهر كرموز | مبعثرة).
_FORMAT_WHATSAPP = (
    "\n\nتنسيق الرد (واتساب):\n"
    "- اكتب رداً قصيراً وبسيطاً بلغة طبيعية. **ممنوع جداول ماركداون** (| و ---) — "
    "واتساب يعرضها كرموز مبعثرة غير مقروءة.\n"
    "- لعنصر واحد: جملة أو سطر واحد (مثل «سعر بيع 195/65/15: 250 شيكل — آخر بيع بتاريخ …»).\n"
    "- لعدة عناصر: أسطر قصيرة، سطر لكل عنصر، بصيغة «الاسم: القيمة». استعمل *نجمة* للتعتيم "
    "عند الحاجة فقط. لا ترقّم الأعمدة ولا تعرض SKU إلا للتمييز الضروري.\n"
    "- تجنّب الحشو: لا مقدمات طويلة ولا شرح للجداول. أعطِ الجواب مباشرة.\n"
)
_FORMAT_WEB = (
    "\n\nتنسيق الرد (ويب):\n"
    "- ردود مرتبة ومختصرة. يمكن استخدام جدول عند تعدد الصفوف، لكن بلا أعمدة معرّفات "
    "داخلية. لخّص المعنى بجملة بعد أي جدول.\n"
)


def _system_prompt(channel: str = "web") -> str:
    from core.assistant_lessons import lessons_text
    from core.assistant_sql import schema_catalog

    fmt = _FORMAT_WHATSAPP if channel == "whatsapp" else _FORMAT_WEB
    prompt = _SYSTEM_PROMPT_BASE + schema_catalog() + fmt
    lessons = lessons_text()
    if lessons:
        prompt += "\n\n" + lessons
    return prompt


def _config():
    base = (getattr(settings, "OLLAMA_BASE_URL", "") or "").strip().rstrip("/")
    key = (getattr(settings, "OLLAMA_API_KEY", "") or "").strip()
    model = (getattr(settings, "OLLAMA_MODEL", "") or "").strip()
    timeout = int(getattr(settings, "OLLAMA_ASSISTANT_TIMEOUT", 120) or 120)
    return base, key, model, timeout


def is_configured() -> bool:
    base, key, model, _ = _config()
    return bool(base and key and model)


# أخطاء عابرة تستحق إعادة محاولة واحدة قصيرة: تقييد لحظي (429) أو خطأ خادم مؤقت
# (5xx) من Ollama، أو انقطاع اتصال عابر — شائعة على الخطة المجانية تحت رسائل متتابعة.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _post_chat(messages: list, tools, base: str, key: str, model: str, timeout: int):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    last_exc = None
    for attempt in range(2):  # محاولة أصلية + إعادة واحدة عند فشل عابر
        try:
            resp = requests.post(
                f"{base}/chat/completions", json=payload, headers=headers, timeout=timeout,
            )
            if resp.status_code in _RETRYABLE_STATUS and attempt == 0:
                logger.warning("ollama %s — إعادة محاولة بعد لحظة", resp.status_code)
                time.sleep(2)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(2)
                continue
            raise
    if last_exc:
        raise last_exc


def chat(user_message: str, tenant, session_key: str | None = None, channel: str = "web") -> str:
    """
    يُجري محادثة كاملة مع النموذج بما فيها جولات الأدوات، ويعيد النص النهائي.
    `tenant` كائن Tenant مُحلَّل مسبقاً من المستدعي (get_tenant للويب، أو
    WhatsAppContact لواتساب) — لا يُشتق هنا ولا داخل الأدوات.
    `session_key` (اختياري) يفعّل ذاكرة المحادثة (core.assistant_memory): آخر
    عدة أدوار من نفس الجلسة تُحقن قبل السؤال الحالي، والسؤال+الجواب يُحفظان
    بعدها. بلا session_key كل نداء مستقل تماماً (السلوك السابق).
    `channel` ("web" أو "whatsapp") يضبط تنسيق الرد — واتساب بلا جداول ماركداون.
    يرفع requests.RequestException / ValueError عند فشل الاتصال — يعالجها المستدعي.
    """
    base, key, model, timeout = _config()
    if not (base and key and model):
        raise RuntimeError(
            "لم تُضبط إعدادات Ollama. أضف OLLAMA_API_KEY و OLLAMA_MODEL في بيئة الخادم."
        )

    history = assistant_memory.get_history(session_key)
    messages = [
        {"role": "system", "content": _system_prompt(channel)},
        *history,
        {"role": "user", "content": user_message},
    ]

    reply = ""
    for _round in range(MAX_TOOL_ROUNDS):
        data = _post_chat(messages, TOOL_SCHEMAS, base, key, model, timeout)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            reply = (msg.get("content") or "").strip()
            break

        # سجّل رسالة المساعد (باستدعاءات الأدوات) ثم نفّذ كل أداة وأعد نتيجتها.
        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            raw_args = fn.get("arguments")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except (json.JSONDecodeError, TypeError):
                args = {}
            result = run_tool(name, args, tenant, session_key=session_key or "")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    else:
        # تجاوزنا حد الجولات — اطلب رداً نصياً أخيراً بلا أدوات.
        data = _post_chat(messages, None, base, key, model, timeout)
        choice = (data.get("choices") or [{}])[0]
        reply = ((choice.get("message") or {}).get("content") or "").strip()

    if session_key and reply:
        assistant_memory.append_turn(session_key, user_message, reply)
    return reply
