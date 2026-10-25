import { expect, test, type Page } from "@playwright/test";

/**
 * TKT-DEV-1 — صورة الجهاز في وضع «تعديل» من نافذة المعاينة.
 *
 * الشاشة داخلية، فتلزم نقاط الدخول الوهمية الثلاث (المستخدم/الشركات/الصلاحيات)
 * كما في `after-sales-warranty.spec.ts`. وما يُثبَت هنا لا يُثبته `tsc` ولا
 * اختبار الوحدة: أن كتابة الرابط **مؤجَّلة** (لا `PATCH` قبل ردّ الرفع)، وأن
 * المسودّة هي ما يُرسَل (إزالة الصورة = `photo_url: ""`)، وأن ردّ رفعٍ يصل بعد
 * «إلغاء» يُهمل، وأن «حفظ» يُعطّل حقل الصورة ما دام `PATCH` في الطيران فلا
 * تعلق إشارة رفعٍ بعد نجاحه.
 *
 * ردُّ الرفع وردُّ `PATCH` **يُفرَج عنهما من الاختبار** (`releaseUpload` ·
 * `releasePatch`) بدل مهلة: ترتيب الأحداث هو المُثبَت، لا سرعة الجهاز. والمحاكي
 * يردّ بشكل `SensitiveDeviceSerializer` ويرفض ما يرفضه الخادم (رابط أطول من
 * 500 حرفاً).
 */

test.use({ serviceWorkers: "block" });

const PROFILE = {
  id: "devices-user",
  name: "مدير الشركة",
  role: "manager",
  email: "devices@example.test",
  employmentStatus: "active",
  isApproved: true,
  isEmailVerified: true,
};

const MEMBERSHIP = {
  id: 42,
  tenant: {
    TenantID: 42,
    CompanyName: "شركة الاختبار",
    SubscriptionPlan: "Enterprise",
    Status: "Active",
    CreatedAt: "2026-07-22T00:00:00Z",
    import_enabled: false,
  },
  role: "manager",
  is_default: true,
  created_at: "2026-07-22T00:00:00Z",
  can_access_import: false,
};

/** التعديل وحده هو موضوع التذكرة — لا إنشاء ولا حذف ولا تدقيق في الشاشة. */
const PERMISSION_KEYS = ["devices.registry.view", "devices.registry.edit"];

const OLD_PHOTO = "https://cdn.test/devices/old.png";
const NEW_PHOTO = "https://cdn.test/devices/new.png";

/** بايتات مولَّدة: لا صورة تُفتح هنا، والمحاكي لا يفحص المحتوى. */
const PHOTO_BYTES = Buffer.from("ktra-device-photo-bytes");

const DEVICE = {
  id: 7,
  customer_name: "زبون تجريبي",
  customer_phone: "0599123456",
  model_name: "جهاز لوحي",
  serial_number: "SN-7",
  imei: "490154203237518",
  technical_notes: "",
  photo_url: OLD_PHOTO,
  status: "registered",
  status_label: "مسجَّل",
  created_by: 1,
  created_by_name: "مدير الشركة",
  created_at: "2026-10-01T09:00:00Z",
  updated_at: "2026-10-01T09:00:00Z",
  deleted_at: null,
  deleted_by_name: "",
  is_deleted: false,
};

type Harness = {
  /** كل `PATCH` وصل الخادم المحاكي — حتى المرفوضَ منها. */
  patchBodies: Record<string, unknown>[];
  /** يُفرَج عن ردّ الرفع؛ يبقى الطلب معلّقاً قبله. */
  releaseUpload: () => void;
  /** يُفرَج عن ردّ `PATCH` حين `holdPatch`؛ وإلا فلا أثر له. */
  releasePatch: () => void;
};

async function mockDevices(
  page: Page,
  opts: { holdPatch?: boolean } = {},
): Promise<Harness> {
  const device: Record<string, unknown> = { ...DEVICE };
  const patchBodies: Record<string, unknown>[] = [];
  let releaseUpload: () => void = () => {};
  const uploadGate = new Promise<void>((resolve) => {
    releaseUpload = resolve;
  });
  // ردُّ الحفظ يُعلَّق عند الطلب فقط — بقية الاختبارات تحفظ بلا انتظار.
  let releasePatch: () => void = () => {};
  const patchGate = opts.holdPatch
    ? new Promise<void>((resolve) => { releasePatch = resolve; })
    : Promise.resolve();

  await page.addInitScript(() => {
    localStorage.setItem("token", "devices-token");
    localStorage.setItem("userId", "devices-user");
    localStorage.setItem("tenantId", "42");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const path = url.pathname;
    const method = route.request().method();
    const json = (body: unknown) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });

    if (path.endsWith("/hr/users/devices-user/")) return json(PROFILE);
    if (path.endsWith("/tenants/companies/my-companies/")) return json([MEMBERSHIP]);
    if (path.endsWith("/permissions/me/")) {
      return json({
        role: "manager",
        is_manager: true,
        permissions: PERMISSION_KEYS,
        modules: { sensitive_devices: true },
      });
    }

    // الرفع معلَّقٌ حتى يقول الاختبار «وصل الردّ».
    if (path.endsWith("/media/upload/")) {
      await uploadGate;
      return json({ url: NEW_PHOTO });
    }

    if (path.endsWith("/devices/records/model_names/")) return json([DEVICE.model_name]);
    if (path.endsWith("/devices/records/")) {
      return json({ count: 1, next: null, previous: null, results: [device] });
    }
    if (/\/devices\/records\/\d+\/$/.test(path)) {
      if (method === "PATCH") {
        const body = JSON.parse(route.request().postData() || "{}") as Record<string, unknown>;
        patchBodies.push(body);
        // نفس ما يرفضه `SensitiveDeviceSerializer`: سقف 500 حرفاً على الرابط.
        if (typeof body.photo_url === "string" && body.photo_url.length > 500) {
          return route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({
              photo_url: ["تأكد من أن هذا الحقل يحتوي على ما لا يزيد عن 500 محرف."],
            }),
          });
        }
        Object.assign(device, body);
        await patchGate;
        return json({ ...device });
      }
      return json(device);
    }

    return json([]);
  });

  return { patchBodies, releaseUpload: () => releaseUpload(), releasePatch: () => releasePatch() };
}

/** يفتح السجل من صفّه، ثم وضع التعديل — بداية كل الاختبارات الأربعة. */
async function openEditMode(page: Page) {
  await page.goto("/sensitive-devices");
  await page.getByRole("button", { name: `معاينة سجل ${DEVICE.imei}` }).click();

  const dialog = page.getByRole("dialog", { name: "معاينة سجل الجهاز" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "تعديل" }).click();
  await expect(dialog.getByTitle("إزالة الصورة")).toBeVisible();
  return dialog;
}

test("رفعٌ مؤجَّل: «حفظ» معطّل حتى يصل الردّ، ثم PATCH يحمل photo_url المُعاد", async ({ page }) => {
  const harness = await mockDevices(page);
  const dialog = await openEditMode(page);

  const preview = dialog.locator('img[alt="صورة الجهاز"]');
  await expect(preview).toHaveAttribute("src", OLD_PHOTO);

  // صندوق المعاينة في التعديل بسقف 224px قريباً من نموذج الاستقبال لا بعرض
  // النافذة كلّها، فلا يقتطع `object-cover` من صورة الهاتف الطولية شريطاً أفقيّاً.
  const previewBox = await preview.locator("xpath=..").boundingBox();
  expect(previewBox).not.toBeNull();
  expect(previewBox!.width).toBeLessThanOrEqual(240);

  await dialog.locator('input[type="file"]').setInputFiles({
    name: "device.png",
    mimeType: "image/png",
    buffer: PHOTO_BYTES,
  });

  const save = dialog.getByRole("button", { name: "حفظ" });
  // الطلب معلّق: «حفظ» معطّل، والمعاينة لم تتغيّر بعد.
  await expect(save).toBeDisabled();
  await expect(preview).toHaveAttribute("src", OLD_PHOTO);
  expect(harness.patchBodies).toEqual([]);

  harness.releaseUpload();

  // الردّ وصل: المعاينة تتبع المسودّة قبل الحفظ، والحفظ يُفتح.
  await expect(preview).toHaveAttribute("src", NEW_PHOTO);
  await expect(save).toBeEnabled();

  await save.click();
  await expect.poll(() => harness.patchBodies.length).toBe(1);
  expect(harness.patchBodies[0].photo_url).toBe(NEW_PHOTO);
  // الحقول الأخرى في الجسم نفسه — لا صورةً وحدها.
  expect(harness.patchBodies[0].status).toBe(DEVICE.status);
  expect(harness.patchBodies[0].customer_name).toBe(DEVICE.customer_name);

  // المعاينة بعد الحفظ تعرض الرابط المحفوظ.
  await expect(dialog.locator('img[alt="صورة الجهاز"]')).toHaveAttribute("src", NEW_PHOTO);
});

test("«إزالة الصورة» ثم «حفظ» يرسل photo_url فارغاً", async ({ page }) => {
  const harness = await mockDevices(page);
  const dialog = await openEditMode(page);

  await dialog.getByTitle("إزالة الصورة").click();
  // الحقل يعود إلى منطقة رفعٍ فارغة — لا معاينة.
  await expect(dialog.locator('img[alt="صورة الجهاز"]')).toHaveCount(0);

  await dialog.getByRole("button", { name: "حفظ" }).click();

  await expect.poll(() => harness.patchBodies.length).toBe(1);
  expect(harness.patchBodies[0].photo_url).toBe("");
});

test("«إلغاء» أثناء الرفع: لا PATCH، والردّ المتأخر لا يلوّث المسودّة", async ({ page }) => {
  const harness = await mockDevices(page);
  const dialog = await openEditMode(page);

  // الرفع صار فعلاً — والإلغاء يأتي بعده لا قبله.
  const uploadRequest = page.waitForRequest((req) => req.url().includes("/media/upload/"));
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "device.png",
    mimeType: "image/png",
    buffer: PHOTO_BYTES,
  });
  await uploadRequest;

  const uploadResponse = page.waitForResponse((res) => res.url().includes("/media/upload/"));
  await dialog.getByRole("button", { name: "إلغاء" }).click();
  await expect(dialog.getByRole("button", { name: "تعديل" })).toBeVisible();

  harness.releaseUpload();
  await uploadResponse;

  // الردّ وصل بعد الإلغاء: لا PATCH. وصندوق القراءة هنا يقرأ المحفوظ
  // (`device.photo_url`) لا المسودّة، فلا يُثبت شيئاً عن تلوّثها — الدليل
  // الحقيقي هو التأكيد التالي بعد إعادة الدخول إلى «تعديل».
  expect(harness.patchBodies).toEqual([]);

  // والعودة إلى وضع التعديل تُظهر القديمة — المسودّة لم تُلوَّث بردّ الرفع المتأخر.
  await dialog.getByRole("button", { name: "تعديل" }).click();
  await expect(dialog.locator('img[alt="صورة الجهاز"]')).toHaveAttribute("src", OLD_PHOTO);
  expect(harness.patchBodies).toEqual([]);
});

test("«حفظ» في الطيران يُعطّل حقل الصورة فلا تعلق إشارة رفعٍ بعده", async ({ page }) => {
  const harness = await mockDevices(page, { holdPatch: true });
  const dialog = await openEditMode(page);

  // صورةٌ حقيقية في المسودّة أوّلاً، كي يكون «حفظ» متاحاً بعد ردّ الرفع.
  const fileInput = dialog.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name: "device.png",
    mimeType: "image/png",
    buffer: PHOTO_BYTES,
  });
  harness.releaseUpload();
  await expect(dialog.locator('img[alt="صورة الجهاز"]')).toHaveAttribute("src", NEW_PHOTO);

  const save = dialog.getByRole("button", { name: "حفظ" });
  const patchRequest = page.waitForRequest((req) => req.method() === "PATCH");
  await save.click();
  await patchRequest;

  // الـPATCH في الطيران: الحقل مقفل، فلا يُختار ملفٌ يرفع إشارة الرفع ثم يُفكَّك
  // الحقل بانتقال الوضع قبل أن ينادي `finally` بـ`onBusyChange(false)`.
  await expect(fileInput).toBeDisabled();

  harness.releasePatch();
  await expect(dialog.getByRole("button", { name: "تعديل" })).toBeVisible();

  // الحارس: العودة إلى «تعديل» تجد «حفظ» متاحاً — الإشارة لم تعلق.
  await dialog.getByRole("button", { name: "تعديل" }).click();
  await expect(dialog.getByRole("button", { name: "حفظ" })).toBeEnabled();
});
