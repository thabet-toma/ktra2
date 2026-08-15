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
    archive_practice_client,
    client_payload,
    create_practice_client,
    create_practice_document,
    create_practice_program,
    create_practice_task,
    delete_practice_document,
    delete_practice_program,
    delete_practice_task,
    document_payload,
    get_practice_client,
    get_practice_settings,
    list_practice_clients,
    list_practice_documents,
    list_practice_programs,
    list_practice_tasks,
    practice_deadlines,
    practice_settings_payload,
    program_payload,
    restore_practice_client,
    task_payload,
    update_practice_client,
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
    "client_id": ("client_not_found", "الزبون غير موجود."),
    "program_id": ("program_not_found", "البرنامج غير موجود."),
    "engagement_id": ("engagement_not_found", "الارتباط غير موجود."),
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
    def get(self, request):
        clients = list_practice_clients(
            accountant=self.accountant,
            status=request.query_params.get("status"),
            search=request.query_params.get("search"),
        )
        return _collection([client_payload(client) for client in clients])

    def post(self, request):
        client = create_practice_client(accountant=self.accountant, data=_payload(request))
        return Response({"client": client_payload(client)}, status=HTTP_201_CREATED)


class PracticeClientDetailView(PracticeView):
    def get(self, request, client_id):
        client = get_practice_client(accountant=self.accountant, client_id=client_id)
        return Response({"client": client_payload(client)})

    def patch(self, request, client_id):
        client = update_practice_client(
            accountant=self.accountant, client_id=client_id, data=_payload(request),
        )
        return Response({"client": client_payload(client)})

    def delete(self, request, client_id):
        """الحذف أرشفة — ملف الزبون تاريخٌ مهني لا يُمحى، فيعود الصفّ في الرد."""
        client = archive_practice_client(accountant=self.accountant, client_id=client_id)
        return Response({"client": client_payload(client)})


class PracticeClientRestoreView(PracticeView):
    def post(self, request, client_id):
        client = restore_practice_client(accountant=self.accountant, client_id=client_id)
        return Response({"client": client_payload(client)})


# ── البرامج ──────────────────────────────────────────────────────────────────


class PracticeProgramListView(PracticeView):
    def get(self, request):
        programs = list_practice_programs(
            accountant=self.accountant,
            client_id=request.query_params.get("client_id"),
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
            client_id=request.query_params.get("client_id"),
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
            client_id=request.query_params.get("client_id"),
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
        client = get_practice_client(accountant=self.accountant, client_id=data.get("client_id"))
        try:
            url = upload_media_file(upload, folder="ktra_practice_documents")
        except MediaUploadError as exc:
            return _error("upload_failed", exc.detail, exc.status_code)
        document = create_practice_document(
            accountant=self.accountant,
            data={
                "client_id": client.pk,
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
