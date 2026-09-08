"""
اشتقاق اسم جهاز الدخول من ترويسة User-Agent.
لا مكتبات خارجية — فحص بسيط وسريع لإنتاج "<المتصفح> على <النظام>".
"""


def derive_device_name(user_agent: str | None) -> str:
    """
    تحويل ترويسة User-Agent إلى اسم مفهوم للمستخدم مثل:
    "Chrome على Windows" أو "Safari على iOS".
    عند الفشل يرجع "جهازٌ غير معروف".
    """
    if not user_agent or not isinstance(user_agent, str):
        return "جهازٌ غير معروف"

    ua = user_agent.strip()
    if not ua:
        return "جهازٌ غير معروف"

    # المتصفحات (الترتيب مهم: Edge و Opera يحملان اسم Chrome/Safari في الـ UA)
    browser = None
    if "Edg/" in ua or "Edge/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser = "Safari"

    # أنظمة التشغيل
    os_name = None
    if "Windows" in ua:
        os_name = "Windows"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua or "iPod" in ua:
        os_name = "iOS"
    elif "Macintosh" in ua or "Mac OS" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"

    if browser and os_name:
        return f"{browser} على {os_name}"
    elif browser:
        return browser
    elif os_name:
        return f"جهاز على {os_name}"

    return "جهازٌ غير معروف"
