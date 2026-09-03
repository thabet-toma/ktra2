"""مكتب المحاسبة — سطح الـAPI تحت `/api/accountant/practice/`.

**لماذا تحت `/api/accountant/`:** `core/permissions.py` يمنع الكتابة التشغيلية على
المحاسب القانوني الخارجي خارج هذه البادئة. سطح المكتب سطح كتابة، فمكانه هنا لا في
مسار جديد — وإلا صار المحاسب ممنوعاً من إدارة زبائنه هو.

**الهوية لا الشركة:** كل صفّ هنا مملوك للمحاسب (`accountant=request.user`)، فلا
هيدر `X-Tenant-Id` مطلوب — تماماً كـ`AccountantMeView`. والعزل يأتي كاملاً من
خدمات `practice.py`: صفّ مكتبٍ آخر يعود «غير موجود» (404) لا «ممنوع» (403).

**العَلَم:** `settings.ACCOUNTANT_PRACTICE_ENABLED` مُطفأً يجعل كل مسار هنا 404 —
لا 403 — فلا يكشف الردُّ وجود سطحٍ مُطفأ.
"""
from django.conf import settings
from django.http import Http404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
)

from accountant_portal.models import AccountantProfile
from accountant_portal.practice import (
    archive_office_partner,
    create_office_partner,
    create_practice_document,
    create_practice_program,
    create_practice_task,
    delete_practice_document,
    delete_practice_program,
    delete_practice_task,
    document_payload,
    get_office_client_view,
    get_office_partner,
    get_practice_settings,
    link_office_partner,
    list_office_partners,
    list_practice_documents,
    list_practice_programs,
    list_practice_tasks,
    practice_dashboard,
    practice_deadlines,
    practice_settings_payload,
    restore_office_partner,
    staff_practice_dashboard,
    program_payload,
    task_payload,
    update_office_partner,
    update_practice_program,
    update_practice_settings,
    update_practice_task,
)
from accountant_portal.services import EngagementConflict
from accountant_portal.views import PortalAPIView, _conflict_response, _error
from core.media_views import MediaUploadError, MediaUploadThrottle, upload_media_file


#: معرّفات تصل من الجسم لا من المسار، فقد تصل غير رقمية. المعرّف غير الرقمي
#: «غير موجود» كسائر المعرّفات المفقودة — لا 500 من `filter(pk="abc")`.
_BODY_ID_KEYS = {
    "partner_id": ("client_not_found", "الزبون غير موجود."),
    "program_id": ("program_not_found", "البرنامج غير موجود."),
    "engagement_id": ("engagement_not_found", "الارتباط غير موجود."),
    "managed_tenant_id": ("managed_tenant_not_found", "الدفتر المُدار غير موجود."),
}


def _payload(request):
    raw = request.data
    if hasattr(raw, "getlist"):  # multipart ⇒ QueryDict
        data = {key: raw.get(key) for key in raw}
    else:
        data = dict(raw) if isinstance(raw, dict) else {}
    for key, (code, detail) in _BODY_ID_KEYS.items():
        if data.get(key) not in (None, ""):
            try:
                data[key] = int(data[key])
            except (TypeError, ValueError) as exc:
                raise EngagementConflict(code, detail, 404) from exc
    return data


def _collection(items):
    return Response({"results": items, "count": len(items)})


class PracticeView(PortalAPIView):
    """أساس مسارات المكتب: العَلَم، ثم المصادقة، ثم ملف المحاسب."""

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        if not getattr(settings, "ACCOUNTANT_PRACTICE_ENABLED", True):
            raise Http404
        super().initial(request, *args, **kwargs)
        try:
            request.user.accountant_profile
        except AccountantProfile.DoesNotExist as exc:
            raise EngagementConflict(
                "accountant_profile_required", "لا يوجد ملف محاسب.", 404,
            ) from exc
        self.accountant = request.user

    def handle_exception(self, exc):
        """`EngagementConflict` رمزٌ ورسالة عربية جاهزان — لا 500 غامض."""
        if isinstance(exc, EngagementConflict):
            return _conflict_response(exc)
        return super().handle_exception(exc)


# ── الزبائن ──────────────────────────────────────────────────────────────────


class PracticeClientListView(PracticeView):
    """ISSUE #86: زبائن المكتب = أطراف شركة المكتب (`partners.Partner`)، مدموجةً
    بمن لم يُرحَّل بعد من `PracticeClient` (سقوط قراءةٍ انتقالي — `list_office_partners`)."""

    def get(self, request):
        clients = list_office_partners(
            accountant=self.accountant,
            search=request.query_params.get("search"),
            status=request.query_params.get("status"),
        )
        return _collection(clients)

    def post(self, request):
        client = create_office_partner(accountant=self.accountant, data=_payload(request))
        return Response({"client": client}, status=HTTP_201_CREATED)


class PracticeClientDetailView(PracticeView):
    """GET يفهم المعرّف السالب (زبونٌ قديمٌ — `get_office_client_view`)؛ PATCH
    صارمةٌ (`update_office_partner`، موجبٌ فقط) — لا كتابة على `PracticeClient`."""

    def get(self, request, client_id):
        return Response({"client": get_office_client_view(accountant=self.accountant, client_id=client_id)})

    def patch(self, request, client_id):
        client = update_office_partner(
            accountant=self.accountant, partner_id=client_id, data=_payload(request),
        )
        return Response({"client": client})

    def delete(self, request, client_id):
        """الحذف أرشفة — حالة طبقة المكتب (`PracticeClientArchive`) لا الطرف."""
        client = archive_office_partner(accountant=self.accountant, partner_id=client_id)
        return Response({"client": client})


class PracticeClientLinkView(PracticeView):
    """ربط زبونٍ بارتباطٍ على المنصة أو بدفترٍ مُدار — فعلٌ حسّاس مستقلّ عن
    تعديل بيانات الاتصال، مطابقٌ لتصميم `OfficeClientLinkForm.tsx`."""

    def patch(self, request, client_id):
        client = link_office_partner(
            accountant=self.accountant, partner_id=client_id, data=_payload(request),
        )
        return Response({"client": client})


class PracticeClientRestoreView(PracticeView):
    def post(self, request, client_id):
        client = restore_office_partner(accountant=self.accountant, partner_id=client_id)
        return Response({"client": client})


# ── البرامج ──────────────────────────────────────────────────────────────────


class PracticeProgramListView(PracticeView):
    def get(self, request):
        programs = list_practice_programs(
            accountant=self.accountant,
            partner_id=request.query_params.get("partner_id"),
            status=request.query_params.get("status"),
        )
        return _collection([program_payload(program) for program in programs])

    def post(self, request):
        program = create_practice_program(accountant=self.accountant, data=_payload(request))
        return Response({"program": program_payload(program)}, status=HTTP_201_CREATED)


class PracticeProgramDetailView(PracticeView):
    def patch(self, request, program_id):
        program = update_practice_program(
            accountant=self.accountant, program_id=program_id, data=_payload(request),
        )
        return Response({"program": program_payload(program)})

    def delete(self, request, program_id):
        delete_practice_program(accountant=self.accountant, program_id=program_id)
        return Response(status=HTTP_204_NO_CONTENT)


# ── المواعيد ─────────────────────────────────────────────────────────────────


class PracticeTaskListView(PracticeView):
    def get(self, request):
        tasks = list_practice_tasks(
            accountant=self.accountant,
            partner_id=request.query_params.get("partner_id"),
            status=request.query_params.get("status"),
        )
        return _collection([task_payload(task) for task in tasks])

    def post(self, request):
        task = create_practice_task(accountant=self.accountant, data=_payload(request))
        return Response({"task": task_payload(task)}, status=HTTP_201_CREATED)


class PracticeTaskDetailView(PracticeView):
    def patch(self, request, task_id):
        task = update_practice_task(
            accountant=self.accountant, task_id=task_id, data=_payload(request),
        )
        return Response({"task": task_payload(task)})

    def delete(self, request, task_id):
        delete_practice_task(accountant=self.accountant, task_id=task_id)
        return Response(status=HTTP_204_NO_CONTENT)


# ── المستندات ────────────────────────────────────────────────────────────────


class PracticeDocumentListView(PracticeView):
    def get(self, request):
        documents = list_practice_documents(
            accountant=self.accountant,
            partner_id=request.query_params.get("partner_id"),
            program_id=request.query_params.get("program_id"),
        )
        return _collection([document_payload(document) for document in documents])


class PracticeDocumentUploadView(PracticeView):
    """رفع مستند إلى ملف الزبون — نفس قلب Cloudinary ونفس حصّته."""

    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [MediaUploadThrottle]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return _error("missing_file", "حقل file مطلوب.", HTTP_400_BAD_REQUEST)
        data = _payload(request)
        # العزل يُفحص **قبل** الرفع: كل رفع يقفل worker طوال رفع Cloudinary
        # المتزامن، فلا يُدفع ثمنه لزبون ليس زبونك.
        client = get_office_partner(accountant=self.accountant, partner_id=data.get("partner_id"))
        try:
            # بلا `tenant`: مستند المكتب يملكه المحاسب لا زبونه — وزبون المكتب
            # قد لا يكون شركةً على المنصة أصلاً. نسبُ بايتاته لشركة الزبون
            # تحمّلها تخزيناً لا تراه ولا تملك حذفه، فيُسجَّل باسم رافعه ويظهر
            # ضمن «غير منسوب» بمجلّده `ktra_practice_documents`.
            url = upload_media_file(
                upload, folder="ktra_practice_documents", uploaded_by=request.user,
            )
        except MediaUploadError as exc:
            return _error("upload_failed", exc.detail, exc.status_code)
        document = create_practice_document(
            accountant=self.accountant,
            data={
                "partner_id": client.pk,
                "program_id": data.get("program_id"),
                "name": str(data.get("name") or "").strip() or getattr(upload, "name", ""),
                "url": url,
            },
        )
        return Response({"document": document_payload(document)}, status=HTTP_201_CREATED)


class PracticeDocumentDetailView(PracticeView):
    def delete(self, request, document_id):
        delete_practice_document(accountant=self.accountant, document_id=document_id)
        return Response(status=HTTP_204_NO_CONTENT)


# ── الإعدادات والأجندة ───────────────────────────────────────────────────────


class PracticeSettingsView(PracticeView):
    def get(self, request):
        return Response({"settings": practice_settings_payload(get_practice_settings(self.accountant))})

    def patch(self, request):
        config = update_practice_settings(accountant=self.accountant, data=_payload(request))
        return Response({"settings": practice_settings_payload(config)})


class PracticeDeadlinesView(PracticeView):
    """أجندة المكتب: البرامج والمواعيد ومواعيد التقديم في قائمة واحدة مرتّبة."""

    def get(self, request):
        return Response(practice_deadlines(accountant=self.accountant))


class PracticeDashboardView(PortalAPIView):
    """لوحة المكتب (ISSUE #58): صاحب المكتب أو موظفٌ مُسنَد — لا مسارٌ ثالث.

    **البوابة مُخفَّفة هنا وحدها** (القرار 7): بقية سطح المكتب (`PracticeView`)
    يرفض 404 بلا `AccountantProfile` — لكن موظف المكتب مستخدمٌ شرعيٌّ لهذا
    المسار تحديداً بلا ملفٍ مهني، فيُردّ 200 بعملائه المُسنَدين (فارغين إن لم
    يُسنَد له شيء) لا 404. كل مسار آخر في هذا الملف يبقى خلف `PracticeView`
    كما هو — لا تخفيفَ هناك.
    """

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        if not getattr(settings, "ACCOUNTANT_PRACTICE_ENABLED", True):
            raise Http404
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, EngagementConflict):
            return _conflict_response(exc)
        return super().handle_exception(exc)

    def get(self, request):
        try:
            request.user.accountant_profile
        except AccountantProfile.DoesNotExist:
            return Response(staff_practice_dashboard(staff=request.user))
        return Response(practice_dashboard(accountant=request.user))
