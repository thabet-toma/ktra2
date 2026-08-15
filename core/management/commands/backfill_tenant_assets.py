"""استرجاع أثري لسجلّ البايتات: ينسب كل أصل Cloudinary مذكور في القاعدة إلى شركته.

سجلّ `core.TenantAsset` يُكتب لحظة الرفع (THA-252)، فكل ما رُفع **قبله** موجودٌ
عند المزوّد بلا صفٍّ يعرف صاحبه ولا حجمه. هذا الأمر يقرأ الروابط المخزَّنة في
القاعدة — وهي وحدها التي تحمل الشركة، لأن الأصل عند Cloudinary لا يحملها — ويسأل
Admin API عن حجم كل معرّف، ثم يكتب الصفوف الناقصة بـ`source='backfill'`.

التشغيل في الإنتاج: **مرّة واحدة بعد النشر**.

    python manage.py backfill_tenant_assets           # عرض فقط، لا يكتب شيئاً
    python manage.py backfill_tenant_assets --yes     # يكتب الصفوف الناقصة

وهو قابل لإعادة التشغيل بلا ضرر: المعرّفات المسجَّلة تُتخطّى قبل أي نداء شبكي،
فالتشغيل الثاني يكتب صفراً. جدولته على cron في cPanel اختيارية — للمصالحة بعد
رفوعٍ فشل تسجيلها — وليست ضرورية للتشغيل العادي.

ما لا يفعله: لا يرفع ولا يحذف ولا ينقل ملفاً واحداً (`uploader.upload` و
`uploader.destroy` غير مستدعيَين هنا إطلاقاً)، ولا يلمس أي عمود خارج
`tenant_assets`. قراءةٌ من Cloudinary وكتابةٌ في جدولٍ واحد، لا أكثر.

سقف المعدّل: الأحجام تُطلب بدفعات من ١٠٠ معرّف في النداء
(`resources_by_ids`)، فبضع عشرات من النداءات تكفي قاعدةً كاملة — بعيداً عن سقف
٥٠٠ نداء/ساعة في الخطة المجانية.

«غير منسوب» في تقرير هذا الأمر = إجمالي `usage()` عند Cloudinary ناقص مجموع
السجلّ: أي بايتات موجودة عند المزوّد ولا يذكرها أي صفٍّ في القاعدة (أصولٌ يتيمة،
أو مسارات رفعٍ خارج التطبيق). وهي كميّة **غير** سطر «غير منسوب» في لوحة المنصة،
وذاك مجموع صفوف السجلّ التي `tenant = NULL` (أصول المنصة ومستندات مكتب المحاسبة).
الاسم واحد والسؤال مختلف، فلا تُقارَن إحداهما بالأخرى.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Sum

# نفس مُحلِّل الرابط الذي يستعمله الحذف — لا نسخة ثانية منه: قاعدةٌ مكرَّرة
# تنحرف عن أصلها بصمت، وانحرافها هنا يعني معرّفاً خاطئاً في السجلّ.
from core.media_views import _parse_cloudinary_ref
from core.models import TenantAsset
from tenants.models import Tenant

# سقف Cloudinary لعدد المعرّفات في نداء `resources_by_ids` الواحد.
API_BATCH = 100
# سقف `IN (...)` عند بناء استعلام «أيّها مسجَّل من قبل؟» — MySQL يتعثّر بقوائم ضخمة.
SQL_IN_CHUNK = 500
# سقف ما يُطبع من الروابط المكسورة؛ العدد الكامل يبقى في السطر الأخير.
BROKEN_SAMPLE = 20

MISSING_CREDS = (
    "اعتماد Cloudinary غير مضبوط: المطلوب CLOUDINARY_CLOUD_NAME و"
    "CLOUDINARY_API_KEY و CLOUDINARY_API_SECRET في البيئة (.env)."
)


@dataclass(frozen=True)
class Surface:
    """سطحٌ في القاعدة يذكر روابط ملفات، ومن أين تُقرأ شركته.

    `tenant_paths` مرتَّبة: أول قيمة غير فارغة تفوز. وقائمةٌ فارغة تعني **أصلاً
    منصّياً بقصد** — لا شركة له، فيُكتب `tenant = NULL`.
    """

    label: str
    model: str
    url_fields: tuple[str, ...] = ()
    json_fields: tuple[str, ...] = ()
    tenant_paths: tuple[str, ...] = ()


# سجلّ الأسطح — كل عمودٍ في القاعدة يُحتمل أن يحمل رابط Cloudinary.
# استُكمل بمسح `res.cloudinary.com` على المستودع كلّه، فأضاف أربعة أعمدة لم تكن
# في الخطة: `LogisticsPayment.invoice_doc` (شقيق `claim_doc` في نفس النموذج)،
# و`SupplierQuotation.attachments`، و`ServiceOrder.photos`. وصور المنتجات ليست
# سطحاً مستقلاً: `store/views.py` يقرأها من `SystemAttachment` أصلاً فهي مشمولة.
REGISTRY: tuple[Surface, ...] = (
    Surface(
        label="مرفقات النظام الموحّدة",
        model="core.SystemAttachment",
        url_fields=("file_path",),
        tenant_paths=("tenant_id",),
    ),
    Surface(
        label="صور الأطراف",
        model="partners.Partner",
        url_fields=("image_path",),
        tenant_paths=("tenant_id",),
    ),
    # الشعار يسكن `TenantSettings` لا `Tenant` — ورقةُ الإعدادات لا بطاقةُ
    # الشركة؛ نسبته عبر `tenant_id` هي نفسها في الحالتين.
    Surface(
        label="شعار الشركة",
        model="tenants.TenantSettings",
        url_fields=("logo_url",),
        tenant_paths=("tenant_id",),
    ),
    Surface(
        label="صور الأجهزة الحسّاسة",
        model="device_registry.SensitiveDevice",
        url_fields=("photo_url",),
        tenant_paths=("tenant_id",),
    ),
    # مرفق سؤال المراجعة يتبع الشركة موضوع السؤال — `ReviewQuery.tenant` مفتاحٌ
    # مباشر إلزامي، فلا التباس هنا.
    Surface(
        label="مرفقات أسئلة المراجعة (بوابة المحاسب)",
        model="accountant_portal.ReviewQuery",
        url_fields=("attachment_url",),
        tenant_paths=("tenant_id",),
    ),
    # مستند مكتب المحاسبة **بلا شركة بقصد**: `PracticeDocument` لا يحمل مفتاح
    # `Tenant` إطلاقاً، وزبون المكتب قد لا يكون شركةً على المنصة أصلاً. وحتى
    # حين يكون مربوطاً بارتباط، الملف يسكن ملفّ المحاسب: الشركة لا تراه ولا
    # تملك حذفه — فتحميلها بايتاته يحاسبها على ما لا تتصرّف فيه. يبقى «غير
    # منسوب»، وهو قرار T1 نفسه.
    Surface(
        label="مستندات مكتب المحاسبة (أصل منصّي)",
        model="accountant_portal.PracticeDocument",
        url_fields=("url",),
        tenant_paths=(),
    ),
    # الدفعة صار لها `tenant` مشتقّ يملؤه `save()`، لكنه `null=True` والصفوف
    # القديمة قد تسبقه — فالصفقة ثم الشحنة احتياطٌ خلفه لا بديلٌ عنه.
    Surface(
        label="مستندات دفعات اللوجستيات",
        model="logistics.LogisticsPayment",
        url_fields=(
            "bank_swift_image",
            "supplier_confirmation_image",
            "claim_doc",
            "invoice_doc",
        ),
        tenant_paths=("tenant_id", "deal__tenant_id", "shipment__tenant_id"),
    ),
    Surface(
        label="مستندات الشحنات",
        model="logistics.LogisticsShipment",
        url_fields=("bill_of_lading_file", "airway_bill_file"),
        tenant_paths=("tenant_id",),
    ),
    Surface(
        label="مرفقات عروض الموردين",
        model="logistics.SupplierQuotation",
        json_fields=("attachments",),
        tenant_paths=("tenant_id",),
    ),
    Surface(
        label="صور أوامر الصيانة",
        model="after_sales.ServiceOrder",
        json_fields=("photos",),
        tenant_paths=("tenant_id",),
    ),
    # ملاحظات التطوير أصلٌ منصّي: يرفعها سوبر أدمن ولا تخصّ شركةً بعينها.
    Surface(
        label="صور ملاحظات التطوير (أصل منصّي)",
        model="core.DevelopmentNote",
        json_fields=("images",),
        tenant_paths=(),
    ),
)


@dataclass
class Record:
    """أصلٌ واحدٌ مرشَّح للسجلّ، مجموعاً من كل مواضع ذكره."""

    public_id: str
    resource_type: str
    folder: str
    tenant_id: int | None = None
    surfaces: set[str] = field(default_factory=set)


@dataclass
class SurfaceStats:
    rows: int = 0
    cloudinary: int = 0
    legacy_http: int = 0
    unparsable: int = 0


def _cloudinary_config() -> tuple[str, str, str]:
    cfg = getattr(settings, "CLOUDINARY_STORAGE", {}) or {}
    return (
        (cfg.get("CLOUD_NAME") or "").strip(),
        (cfg.get("API_KEY") or "").strip(),
        (cfg.get("API_SECRET") or "").strip(),
    )


def _all_rows(model):
    """كل الصفوف، بما فيها المحذوف ناعماً.

    الحذف الناعم يُخفي الصفّ عن التطبيق ولا يمحو الملف من Cloudinary: بايتاته
    ما زالت مدفوعة الثمن ومنسوبةً لشركةٍ ما. استبعادها هنا يُنقص تلك الشركة
    ويُضخّم «غير منسوب» — ونقصٌ في رقمٍ لا أحد يجمعه يدوياً لا يُلاحَظ أبداً.
    """
    return getattr(model, "all_objects", None) or model._base_manager


def _json_urls(value: Any) -> Iterator[str]:
    """روابط قائمة JSON: عنصرها إمّا نصٌّ صريح أو قاموسٌ فيه `url`.

    الشكلان قائمان فعلاً — `SupplierQuotation.attachments` و`DevelopmentNote.images`
    قواميس `{url, …}` يفرضها مُسلسِلهما، بينما `ServiceOrder.photos` حقلٌ حرّ بلا
    شكلٍ مفروض. قبولُ الاثنين أرخص من خسارة صفٍّ لأن شكله لم يكن المتوقَّع.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, str) and item.strip():
            yield item.strip()
        elif isinstance(item, dict):
            for key in ("url", "secure_url", "file_path", "path"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    yield candidate.strip()
                    break


def _folder_of(public_id: str) -> str:
    return public_id.rsplit("/", 1)[0] if "/" in public_id else ""


class Command(BaseCommand):
    help = (
        "يملأ سجلّ core.TenantAsset بالأصول القديمة: يمسح روابط Cloudinary "
        "المخزَّنة في القاعدة، يسأل Admin API عن أحجامها، وينسبها لشركاتها. "
        "عرضٌ فقط بلا --yes. يُشغَّل مرّة بعد النشر، وإعادته آمنة."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="اكتب الصفوف فعلاً (الافتراضي: عرض فقط بلا كتابة).",
        )

    # ── المسح ─────────────────────────────────────────────────────────────
    def _scan(self) -> tuple[dict[str, Record], dict[str, SurfaceStats], list[str]]:
        records: dict[str, Record] = {}
        stats: dict[str, SurfaceStats] = {}
        conflicts: list[str] = []

        for surface in REGISTRY:
            stat = stats.setdefault(surface.label, SurfaceStats())
            model = apps.get_model(surface.model)
            columns = (*surface.url_fields, *surface.json_fields, *surface.tenant_paths)
            for row in _all_rows(model).values(*columns).iterator(chunk_size=2000):
                stat.rows += 1
                tenant_id = next(
                    (row[path] for path in surface.tenant_paths if row.get(path)), None
                )
                urls: list[str] = []
                for name in surface.url_fields:
                    value = row.get(name)
                    if isinstance(value, str) and value.strip():
                        urls.append(value.strip())
                for name in surface.json_fields:
                    urls.extend(_json_urls(row.get(name)))

                for url in urls:
                    if not url.startswith(("http://", "https://")):
                        continue
                    if "res.cloudinary.com" not in url:
                        # روابط Firebase القديمة: تُعدّ ولا يُخمَّن لها حجم.
                        stat.legacy_http += 1
                        continue
                    public_id, rtype = _parse_cloudinary_ref(url)
                    if not public_id:
                        stat.unparsable += 1
                        continue
                    stat.cloudinary += 1
                    record = records.get(public_id)
                    if record is None:
                        record = Record(
                            public_id=public_id,
                            resource_type=rtype or "image",
                            folder=_folder_of(public_id),
                            tenant_id=tenant_id,
                        )
                        records[public_id] = record
                    elif (
                        tenant_id is not None
                        and record.tenant_id is not None
                        and tenant_id != record.tenant_id
                    ):
                        # نفس الملف مذكورٌ في شركتين: يُحسب لأولى ذاكرتيه ويُبلَّغ
                        # عنه — البايتات لا تُنسخ عند المزوّد فلا تُحتسب مرتين.
                        conflicts.append(
                            f"{public_id}: {record.tenant_id} / {tenant_id}"
                        )
                    elif record.tenant_id is None:
                        record.tenant_id = tenant_id
                    record.surfaces.add(surface.label)

        return records, stats, conflicts

    def _already_ledgered(self, public_ids: list[str]) -> set[str]:
        known: set[str] = set()
        for start in range(0, len(public_ids), SQL_IN_CHUNK):
            chunk = public_ids[start : start + SQL_IN_CHUNK]
            known.update(
                TenantAsset.objects.filter(public_id__in=chunk).values_list(
                    "public_id", flat=True
                )
            )
        return known

    # ── Cloudinary ────────────────────────────────────────────────────────
    def _fetch_sizes(
        self, records: list[Record]
    ) -> tuple[dict[str, tuple[int, str]], list[str]]:
        """أحجام حقيقية من Admin API، بدفعات ١٠٠ لكل نوع مورد.

        ما لا يعود من المزوّد لا يُكتب: رابطٌ في القاعدة بلا أصلٍ خلفه رابطٌ
        مكسور، وكتابة `bytes=0` له تضع رقماً يبدو مقيساً وهو ليس كذلك.
        """
        import cloudinary
        import cloudinary.api

        by_type: dict[str, list[str]] = defaultdict(list)
        for record in records:
            by_type[record.resource_type or "image"].append(record.public_id)

        sizes: dict[str, tuple[int, str]] = {}
        for rtype, ids in by_type.items():
            for start in range(0, len(ids), API_BATCH):
                chunk = ids[start : start + API_BATCH]
                response = cloudinary.api.resources_by_ids(
                    chunk, resource_type=rtype, type="upload"
                )
                for item in response.get("resources", []) or []:
                    public_id = item.get("public_id")
                    if public_id:
                        sizes[public_id] = (
                            int(item.get("bytes") or 0),
                            (item.get("resource_type") or rtype)[:20],
                        )

        broken = [r.public_id for r in records if r.public_id not in sizes]
        return sizes, broken

    def _account_usage(self) -> int | None:
        """إجمالي التخزين عند المزوّد — يُطلب مرّةً واحدة في نهاية التقرير."""
        import cloudinary
        import cloudinary.api

        try:
            usage = cloudinary.api.usage() or {}
        except Exception as exc:  # لا يُسقط تقريراً اكتمل عمله الحقيقي
            self.stdout.write(self.style.WARNING(f"تعذّر قراءة usage(): {exc}"))
            return None
        storage = usage.get("storage") or {}
        value = storage.get("usage") if isinstance(storage, dict) else None
        return int(value) if value is not None else None

    # ── التنفيذ ───────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        write = bool(options["yes"])
        cloud_name, api_key, api_secret = _cloudinary_config()
        configured = all([cloud_name, api_key, api_secret])

        # الكتابة بلا اعتماد ممنوعة قبل أي عمل: صفٌّ بـ`bytes=0` كتبه نداءٌ لم
        # يحدث هو رقمٌ كاذبٌ في سجلٍّ الغرضُ منه أن يُوثَق به.
        if write and not configured:
            raise CommandError(MISSING_CREDS)

        records, stats, conflicts = self._scan()
        self._print_scan(stats)

        pending = list(records.values())
        known = self._already_ledgered([r.public_id for r in pending])
        pending = [r for r in pending if r.public_id not in known]

        self.stdout.write("")
        self.stdout.write(
            f"أصول Cloudinary مميَّزة: {len(records)} · "
            f"مسجَّلة من قبل: {len(known)} · مرشَّحة للكتابة: {len(pending)}"
        )
        if conflicts:
            self.stdout.write(
                self.style.WARNING(
                    f"أصولٌ مذكورة في أكثر من شركة: {len(conflicts)} "
                    f"(تُحتسب لأولاها) — {conflicts[0]}"
                )
            )

        if not configured:
            # العرض بلا اعتماد يبقى مفيداً: الجرد من القاعدة حقيقي، وما ينقصه
            # الأحجام وحدها. يُقال صراحةً بدل أن يُقرأ التقرير كأنه مكتمل.
            self._print_tenants(pending, {}, write=False, sizes_known=False)
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(MISSING_CREDS))
            self.stdout.write(
                self.style.WARNING(
                    "الجرد أعلاه من القاعدة وحدها — بلا أحجام وبلا إجمالي "
                    "المزوّد، ولا صفَّ يُكتب. اضبط المفاتيح ثم أعد التشغيل."
                )
            )
            return

        import cloudinary

        cloudinary.config(
            cloud_name=cloud_name, api_key=api_key, api_secret=api_secret
        )

        sizes, broken = self._fetch_sizes(pending)
        writable = [r for r in pending if r.public_id in sizes]

        created = 0
        if write and writable:
            created = len(
                TenantAsset.objects.bulk_create(
                    [
                        TenantAsset(
                            tenant_id=r.tenant_id,
                            public_id=r.public_id[:191],
                            bytes=sizes[r.public_id][0],
                            resource_type=sizes[r.public_id][1],
                            folder=r.folder[:200],
                            source="backfill",
                        )
                        for r in writable
                    ],
                    batch_size=500,
                    ignore_conflicts=True,
                )
            )

        self._print_tenants(writable, sizes, write=write, sizes_known=True)

        if broken:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(f"روابط مكسورة (في القاعدة وليست عند المزوّد): {len(broken)}")
            )
            for public_id in broken[:BROKEN_SAMPLE]:
                self.stdout.write(f"  - {public_id}")
            if len(broken) > BROKEN_SAMPLE:
                self.stdout.write(f"  … و{len(broken) - BROKEN_SAMPLE} غيرها")

        self._print_totals(writable, sizes, write)

        self.stdout.write("")
        if write:
            self.stdout.write(self.style.SUCCESS(f"كُتب {created} صفّاً في السجلّ."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"عرضٌ فقط — لم يُكتب شيء. {len(writable)} صفّاً جاهزاً؛ "
                    "أعد التشغيل بـ--yes للكتابة."
                )
            )

    # ── التقرير ───────────────────────────────────────────────────────────
    def _print_scan(self, stats: dict[str, SurfaceStats]) -> None:
        self.stdout.write("--- المسح حسب السطح ---")
        for label, stat in stats.items():
            self.stdout.write(
                f"  {label}: صفوف={stat.rows} · Cloudinary={stat.cloudinary} · "
                f"روابط قديمة (غير Cloudinary)={stat.legacy_http} · "
                f"غير مقروءة={stat.unparsable}"
            )

    def _ledger_by_tenant(
        self,
        pending: list[Record],
        sizes: dict[str, tuple[int, str]],
        *,
        write: bool,
    ) -> dict[int | None, list[int]]:
        """السجلّ لكل شركة **بعد** هذا التشغيل، لا حصّة التشغيل وحدها.

        سؤال المالك «كم تستهلك كل شركة؟» لا يُجاب بما أضافه تشغيلٌ بعينه: إعادةُ
        التشغيل تضيف صفراً فيبدو الجواب صفراً. ولأن «غير منسوب» أسفل التقرير
        يُطرح من مجموع السجلّ كلّه، فبقاء الجدولين على أساسين مختلفين يجعل أرقام
        التقرير الواحد غير قابلة للجمع.
        """
        per_tenant: dict[int | None, list[int]] = defaultdict(lambda: [0, 0])
        for row in TenantAsset.objects.values("tenant_id").annotate(
            files=Count("id"), total=Sum("bytes")
        ):
            per_tenant[row["tenant_id"]] = [row["files"], row["total"] or 0]
        if not write:
            # لم تُكتب بعد، فتُضاف حسابياً كي يرى المالك ما سيصير إليه الرقم.
            for record in pending:
                bucket = per_tenant[record.tenant_id]
                bucket[0] += 1
                bucket[1] += sizes.get(record.public_id, (0, ""))[0]
        return per_tenant

    def _print_tenants(
        self,
        pending: list[Record],
        sizes: dict[str, tuple[int, str]],
        *,
        write: bool,
        sizes_known: bool,
    ) -> None:
        names = dict(Tenant.objects.values_list("TenantID", "CompanyName"))
        per_tenant = self._ledger_by_tenant(pending, sizes, write=write)

        self.stdout.write("")
        self.stdout.write("--- حسب الشركة ---")
        if not per_tenant:
            self.stdout.write("  (لا شيء)")
            return
        for tenant_id, (count, total) in sorted(
            per_tenant.items(), key=lambda kv: (kv[0] is not None, kv[0] or 0)
        ):
            label = (
                "غير منسوب (أصول المنصة ومكتب المحاسبة)"
                if tenant_id is None
                else f"{names.get(tenant_id, '?')} (#{tenant_id})"
            )
            # بلا اعتماد لا حجم — و«0 بايت» هنا يُقرأ كقياسٍ وهو جهل.
            size_text = f"{total:,} بايت" if sizes_known else "الحجم غير معروف"
            self.stdout.write(f"  {label}: {count} ملف · {size_text}")

    def _print_totals(
        self,
        records: list[Record],
        sizes: dict[str, tuple[int, str]],
        write: bool,
    ) -> None:
        new_bytes = sum(sizes.get(r.public_id, (0, ""))[0] for r in records)
        stored = TenantAsset.objects.aggregate(total=Sum("bytes"))["total"] or 0
        # في العرض المجرَّد لم تُكتب الصفوف بعد، فالسجلّ المتوقَّع = القائم + الجديد.
        ledger = stored if write else stored + new_bytes
        usage_total = self._account_usage()

        self.stdout.write("")
        self.stdout.write("--- الإجمالي ---")
        self.stdout.write(f"  مجموع السجلّ بعد هذا التشغيل: {ledger:,} بايت")
        if usage_total is None:
            self.stdout.write("  إجمالي Cloudinary: غير متاح")
            return
        self.stdout.write(f"  إجمالي Cloudinary (usage): {usage_total:,} بايت")
        remainder = usage_total - ledger
        self.stdout.write(
            f"  «غير منسوب» عند المزوّد (usage - السجلّ): {remainder:,} بايت"
        )
        self.stdout.write(
            "  (هذا الرقم غير سطر «غير منسوب» في لوحة المنصة — ذاك صفوفٌ "
            "tenant=NULL داخل السجلّ، وهذا بايتاتٌ لا يذكرها السجلّ أصلاً.)"
        )
