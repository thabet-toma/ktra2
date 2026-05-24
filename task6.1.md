# TASK6.1 — Import Flow Editor: تَحويل ImportDocumentScreen لشاشة موحَّدة قابلة للتَّحرير

> **الدور:** موديل أرخص يُنفِّذ خطّة موافق عليها من المالك.
> **التاريخ:** 2026-05-24. **المرجع:** task6.md (P-G-1..G-3) + كود
> `ImportDocumentScreen.tsx` الموجود (read-only) + الـforms الحاليّة
> (`ShipmentForm.tsx`، `CustomsClearanceManagement.tsx`،
> `LocalShippingPage.tsx`).
> **القاعدة الذهبية:** اقرأ هذا الملف كاملاً + اقرأ `task6.md` قسم
> «الفئة 0» + اقرأ `ImportDocumentScreen.tsx` الحالي قبل أيّ سَطر كود.

---

## السياق (لماذا هذه التاسك موجودة)

`task6.md P-G-1` طَلَب «شاشة موحَّدة» تَدمج رحلة الاستيراد (شحنة +
تخليص + نقل محلي + فاتورة) في صفحة واحدة كَثيفة. الموديل السابق نَفَّذ
**`ImportDocumentScreen.tsx`** لكنّها **read-only فقط** — تَعرض البيانات
ولا تُحرِّرها. النتيجة:

1. المستخدم لا يَزال يَفتح `ShipmentForm.tsx` للتَّحرير (8 sections
   عمودياً + scroll مستمر — نفس المرض الذي شَكا منه المالك).
2. التخليص والنقل المحلي لَسّا في شاشات منفصلة.
3. الـtwo screens (الجديدة read-only + القديمة editable) تَخلق ارتباكاً.

**الهدف:** تَحويل `ImportDocumentScreen` لمحرِّر كامل بحيث يَستبدل
الـ3 forms القديمة فعلاً. بعد هذه التاسك، الـforms القديمة تُحذَف.

---

## القواعد الذهبية (إلزامية — اقرأها مرّتَيْن)

1. **0 ميزات backend جديدة.** كل الـAPIs و models موجودة من task6 P-D..P-F.
2. **0 dependencies جديدة.** استَخدم react-router-dom و lucide-react و
   الـaseel primitives الموجودة فقط.
3. **commit-per-sub-phase** بـرسالة `task6.1 A-1: <description>` إلخ.
4. **اقرأ `ImportDocumentScreen.tsx` كاملاً** قبل أيّ تَعديل — فيها كل
   الـtabs الـ7 الموجودة.
5. **استَخدم نفس الـserializer endpoints** الموجودة من task6:
   - `apiPatchObject('logistics/shipments/<id>/', ...)` لـshipment
   - `updateClearance(id, patch)` من `clearanceApi.ts` لـclearance
   - `updateLocalShipment(...)` من `localShippingApi.ts` لـlocal
   - `patchShippingWorkflow(...)` من `shipmentsService.ts` لـworkflow
6. **لا تَخترع API جديد** — إن وَجدت شيء ناقص، علِّق `[QUESTION]` ولا
   تَفترض.
7. **بعد كل sub-phase، شغِّل `npx tsc --noEmit`** وتَأكَّد أن العَدّاد
   لا يَرتفع.
8. **حَذف `ShipmentForm.tsx` آخر خُطوة فقط** بعد التَحقّق من editing
   parity — لا تَحذفه مبكراً.
9. **القاعدة الحاكمة:** بَعد هذه التاسك، رحلة الاستيراد كاملة
   (إنشاء شحنة → تخليص → نقل → فاتورة) تَتمّ من شاشة `ImportDocumentScreen`
   وحدها بدون فَتح أيّ شاشة قديمة.
10. **اقرأ `docs/ui_density_rules.md` و `task6.md` P-G-14** — كل tab
    يَجب يَلتزم بقواعد الكَثافة.

---

## Pre-Planning Protocols (الـ5 إلزامية — نَفس task6.md)

### 1. الوعي الزمني وموثوقية التبعيات
- التاريخ 2026-05-24. لا libs جديدة. react-router-dom + lucide-react
  + aseel primitives = الـtoolkit الكامل.

### 2. التدفّق المنطقي ومنع زحف الميزات
- صفر ميزات جديدة. **تَحويل** فقط: read-only → editable.
- إن طَلَب شيء يَتطلَّب backend جديد، علِّق `[QUESTION]` ولا تُنفِّذ.

### 3. المعمارية الذكية (Surgical)
- `ImportDocumentScreen.tsx` يَبقى single file (لا split لـmultiple).
- كل tab يَكون `<ImportFlowDealsTab />`، `<ImportFlowClearanceTab />`,
  `<ImportFlowLocalTab />` إلخ — sub-components داخل `import-flow/` dir.
- formData state واحد على مستوى الـscreen، lift up لـsiblings.

### 4. التتبّع (Safe Logging)
- لا `console.log` في commits — الأخطاء تَذهب لـsetError state.

### 5. الذاكرة الخارجية
- بعد كل sub-phase، حَدِّث `PROJECT_MAP.md` قسم `[TASK6 — P-G PROGRESS]`.

---

## Milestones A .. I

> **Total:** 9 sub-phases · ~28 task · 0 backend migration ·
> 3 forms يُحذَف في النهاية. **التقدير:** 8-12 ساعة موديل أرخص +
> 2 ساعة مراجعة.

---

### A — Shipment Editable Header (1.5h)

> **الهدف:** الـheader band في ImportDocumentScreen يَصير editable
> بدل readonly. Save button يُفعَّل + يُرسل PATCH.

- [ ] **A-1 — formData state لـshipment.**
  في `ImportDocumentScreen.tsx`:
  - أَضِف `const [shipmentForm, setShipmentForm] = useState<ShipmentApiRow | null>(null)`.
  - في الـuseEffect بعد `setShipment(s)` أَضِف `setShipmentForm({ ...s })`.
  - **لا تَستبدل** `shipment` state — `shipment` يَبقى للـsnapshot الأصلي،
    `shipmentForm` للتَّحرير.

- [ ] **A-2 — Editable inputs in header band.**
  حَوِّل كل `readOnly value={s.X}` لـ`value={shipmentForm?.X || ""}
  onChange={(e) => setShipmentForm(prev => prev ? { ...prev, X: e.target.value } : prev)}`.
  - استَثنِ الحقول read-only الحقيقيّة: `رقم الإرسالية`, `الحجم/الوزن`
    (computed)، `رقم القيد`، `كشف الضريبة`، `محرَّر` (computed من
    `editable` flag — راجع المالك).

- [ ] **A-3 — Save button + handler.**
  - أَضِف toolbar action `{ key: "save", label: "تخزين (F12)",
    icon: <Save />, onClick: handleSave }`.
  - `handleSave`:
    ```ts
    const handleSave = async () => {
      if (!shipmentForm) return;
      setSaving(true); setError(null);
      try {
        const patched = await apiPatchObject<ShipmentApiRow>(
          `logistics/shipments/${shipmentForm.id}/`,
          shipmentForm,
          { tenantId: tid() }
        );
        setShipment(patched);
        setShipmentForm({ ...patched });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setSaving(false);
      }
    };
    ```

- [ ] **A-4 — Dirty state + before-unload guard.**
  - `isDirty = JSON.stringify(shipment) !== JSON.stringify(shipmentForm)`.
  - Save button `disabled={!isDirty || saving}`.
  - `useEffect` يَستمع `beforeunload` ويَمنع إغلاق الصفحة لو `isDirty`.

- [ ] **A-5 — New shipment case (shipmentId=null).**
  - لو `shipmentId === null`: ابدأ بـ`shipmentForm = { id: 0, ... defaults }`.
  - Save → `apiPostObject('logistics/shipments/', shipmentForm)` بدل PATCH.
  - بَعد الـPOST يَأتي ID جديد → `navigate('/import-flow/' + newId)`.

**Verifiable A:** فَتح شحنة موجودة، تَعديل حقل، ضَغط تخزين، رَفرَش —
التعديل ثابت. إنشاء شحنة جديدة من `/import-flow/new` ثم تخزين →
يَنتقل لـURL بـID جديد.

---

### B — Clearance Tab Editable (2h)

> **الهدف:** tab «التخليص» يَصير محرِّر كامل لبيانات `LogisticsClearance` +
> بنود `LogisticsClearanceLine` (P-D-1).

- [ ] **B-1 — Clearance formData state.**
  - `const [clearanceForm, setClearanceForm] = useState<ClearanceRow | null>(null)`.
  - في الـuseEffect بعد `setClearance(matched)` أَضِف `setClearanceForm({ ...matched })`.

- [ ] **B-2 — Editable clearance header.**
  في tab «التخليص»، أَضِف header band ثاني (4×3 = 12 حقل) قبل جدول البنود:
  - رقم البيان (declaration_number)
  - تاريخ التخليص (clearance_date)
  - الوقت (transaction_time) — P-F-1
  - تاريخ ثاني (second_date) — P-F-1
  - رقم فاتورة المقاصة (settlement_invoice_number) — P-F-1
  - مشتغل مرخص (licensed_dealer_no) — P-F-1
  - المخلِّص (customs_broker FK)
  - العملة (currency FK) — P-F-1
  - سعر العملة (exchange_rate) — P-F-1
  - مجموع بدون ضريبة (subtotal_no_vat) — P-F-1
  - مجموع الضريبة (vat_total) — P-F-1
  - الإجمالي (grand_total) — P-F-1

- [ ] **B-3 — Editable clearance lines table.**
  - استَخدم `AseelGrid` (موجود من task5) للجدول.
  - أعمدة: # / النوع (line_type choice) / البيان / مدين / دائن /
    VAT% / مركز التكلفة / [حذف].
  - زر «إضافة بند» يُضيف row فارغة لـ`clearanceForm.lines`.
  - زر «حذف» يَزيل الـrow.
  - lookup `line_type` choices من `clearanceDefaults.ts` (LINE_TYPE_LABELS).

- [ ] **B-4 — Save clearance.**
  - `handleSaveClearance`:
    ```ts
    await updateClearance(clearanceForm.id, {
      declaration_number, clearance_date, transaction_time,
      second_date, settlement_invoice_number, licensed_dealer_no,
      customs_broker, currency, exchange_rate,
      subtotal_no_vat, vat_total, grand_total,
      cost_lines: clearanceForm.lines.map(l => ({
        label: l.description, amount: l.debit - l.credit,
      })),
    });
    ```
  - الـcost_lines payload يَستخدم الـbackwards-compat JSON shape
    (راجع task6 P-D-3) — الـbackend يُحوِّله لـrows عبر
    `_sync_lines_from_cost_lines`.

- [ ] **B-5 — Create new clearance if shipment has none.**
  - لو `clearance === null`: في tab «التخليص» اعرض زر «إنشاء سجل تخليص».
  - النقر → `createClearance({ shipment: shipment.id, ... })` من
    `clearanceApi.ts` ثم `setClearance(new)` + `setClearanceForm(new)`.

**Verifiable B:** فَتح شحنة، tab «التخليص» يُحرَّر header + بنود،
تخزين، إعادة فتح → تَعديل ثابت. شحنة بدون تخليص → زر «إنشاء» يَعمل،
ينشئ سجل تخليص جديد، يَفتح لـediting.

---

### C — Deals Tab Editable (1.5h)

> **الهدف:** tab «الصفقات» يَدير ربط الصفقات بالشحنة + تَوزيع التكاليف.

- [ ] **C-1 — Load shipment deals.**
  في `useEffect` للـload، أَضِف:
  ```ts
  const sd = await apiGetList<ShipmentDealRow>(
    `logistics/shipment-deals/`, { tenantId: tid(), params: { shipment: s.id } }
  );
  setShipmentDeals(sd);
  ```
  + `interface ShipmentDealRow { id: number; deal: number; deal_ref: string;
     deal_name?: string; allocation_pct: number; allocated_cost: number; }`

- [ ] **C-2 — Table view in deals tab.**
  استَخدم `AseelDenseTable` (task5 N9):
  - أعمدة: رقم الصفقة / الاسم / نسبة التَّوزيع / حصة التكلفة /
    [إلغاء الربط].

- [ ] **C-3 — Link deal button.**
  زر «ربط صفقة» يَفتح `AseelIndexPicker` بـlist الصفقات المتاحة
  (`listDeals({ status: 'open', shipment: null })`).
  اختيار → POST لـ`logistics/shipment-deals/` بـ`{shipment, deal,
  allocation_pct: 100/n}`.

- [ ] **C-4 — Edit allocation pct.**
  حقل `allocation_pct` editable inline في الجدول. blur → PATCH.
  مجموع النسب يَجب 100% — تَحقَّق front-end (Toast إن مش 100).

- [ ] **C-5 — Unlink button.**
  DELETE `logistics/shipment-deals/<id>/` ثم `setShipmentDeals(prev =>
  prev.filter(...))`.

**Verifiable C:** ربط 3 صفقات بشحنة، تَوزيع 50/30/20، تخزين،
رَفرَش → النسب صحيحة. إلغاء ربط صفقة → الصفقة تختفي من الجدول.

---

### D — Local Shipments Tab Editable (1.5h)

> **الهدف:** tab «النقل المحلي» يَصير محرِّر كامل لـ`LocalShipment` records
> المرتبطة بالشحنة.

- [ ] **D-1 — formData per local row.**
  - `[localForm, setLocalForm] = useState<LocalShipmentRow | null>(null)` —
    للسجل المُحرَّر حالياً.
  - row click في الجدول → `setLocalForm(row)`.
  - زر «إضافة» → `setLocalForm({ id: 0, shipment: s.id, ...defaults })`.

- [ ] **D-2 — Inline form below the list.**
  لو `localForm`: اعرض compact 3×4 grid (12 حقل):
  - رقم النقل (auto)
  - الناقل (carrier FK)
  - السائق (driver_name)
  - المركبة (vehicle_number)
  - الأصل (origin)
  - الوجهة (destination)
  - تاريخ الالتقاط (pickup_date)
  - تاريخ التسليم (delivery_date)
  - المبلغ (amount)
  - العملة (currency FK)
  - نوع الدفع (payment_type)
  - الحالة (status)

- [ ] **D-3 — Save / cancel buttons.**
  - تخزين → `createLocalShipment` أو `updateLocalShipment`.
  - إلغاء → `setLocalForm(null)`.
  - بعد التخزين → `reload local shipments`.

- [ ] **D-4 — Post journal action.**
  زر «ترحيل» للسجل المرحَّل (`is_posted=false`). يَستدعي
  `postLocalShipment(id)` (موجود في `localShippingApi.ts`).

**Verifiable D:** فَتح شحنة، إضافة نقل محلي، تخزين، ترحيل → القيد
يَظهر في accounting. تَعديل سجل قائم → التعديل ثابت.

---

### E — Payments Tab Editable (1h)

> **الهدف:** tab «الدفعات» يَدير دفعات التخليص (clearance fees vs
> shipping).

- [ ] **E-1 — Add payment button.**
  لو clearance موجود: زر «إضافة دفعة» يَفتح compact form (4 حقل):
  - المبلغ
  - الغرض (payment_purpose choice من P-D-5)
  - تاريخ
  - ملاحظات

- [ ] **E-2 — Post via existing endpoint.**
  استَخدم endpoint موجود من task6:
  `POST /api/logistics/clearances/<id>/pay_from_cashbox/` بـpayload
  `{ amount, payment_kind: 'shipping' or 'clearance', payment_date, notes }`.
  بَعد النجاح: reload payments.

- [ ] **E-3 — Status indicator per payment.**
  جدول الدفعات يَعرض `is_posted` + `journal_id`. زر «إلغاء ترحيل»
  للدفعات المرحَّلة (يَحتاج `[QUESTION]` للمالك — موجود endpoint؟).

**Verifiable E:** إضافة دفعة شحن، تخزين، تَنعكس في الـright dock
totals. الـpayments قائمة تَزداد.

---

### F — Convert to Purchase Invoice (1h)

> **الهدف:** زر «تكوين فاتورة» يَنشئ PurchaseInvoice من بيانات الشحنة
> + التخليص + الصفقات.

- [ ] **F-1 — Button in toolbar.**
  `{ key: "to-invoice", label: "تكوين فاتورة", icon: <FileText />,
    onClick: handleCreateInvoice, disabled: !shipment?.id ||
    shipment.shipment_type === 'transport' }`.

- [ ] **F-2 — Create invoice handler.**
  - إن endpoint موجود من task6 (`POST /api/logistics/purchase-invoices/from-shipment/<id>/`):
    استَخدمه.
  - وإلا: POST عادي لـ`logistics/purchase-invoices/` بـ`{
      converted_from_shipment: shipment.id,
      converted_at: now, converted_by: currentUser.id,
      ... pre-fill من shipment + clearance + deals
    }`.
  - بَعد النجاح: `window.open('/purchase-invoices/<new_id>')`.

- [ ] **F-3 — Visual link if invoice exists.**
  - لو الشحنة مَربوطة بفاتورة (راجع API)، اعرض badge في الـheader:
    «فاتورة #X». النقر → يَفتحها.

**Verifiable F:** شحنة بـclearance مكتمل → زر «تكوين فاتورة» يُنشئ
PurchaseInvoice محشورة بالـlines + landed costs + grand_total.

---

### G — Routing Migration (45 دقيقة)

> **الهدف:** بَعد التحقّق من editing parity، حَوِّل الـrouting
> ليَستهلك ImportDocumentScreen كَمحرِّر افتراضي.

- [ ] **G-1 — Restore `/import-flow/:id` redirect from ShipmentManagement.**
  في `ShipmentManagement.tsx:173` (`handleEdit`):
  ```ts
  navigate(`/import-flow/${encodeURIComponent(String(shipment.id))}`);
  ```
  (تَمَّ revert سابقاً للـhotfix — أَعِده بَعد التَحقّق أن A..F تَعمل).

- [ ] **G-2 — Clearance row click → import-flow.**
  في `CustomsClearanceManagement.tsx`:
  - في الـtable `onRowClick={(row) => navigate('/import-flow/' +
    row.shipment + '?tab=clearance')}`.
  - الـclearance form الجانبي يَبقى للعرض السريع، لكن الـtoolbar
    «تعديل تفصيلي» يَنقل لـimport-flow.

- [ ] **G-3 — Local shipping row click → import-flow.**
  في `LocalShippingPage.tsx`:
  - row click → `navigate('/import-flow/' + row.shipment +
    '?tab=local')`.

- [ ] **G-4 — Query param tab parsing.**
  في `ImportDocumentScreen.tsx`:
  ```ts
  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') || 'deals';
  ```
  مَرِّره لـ`<AseelDocumentShell tabs={...} initialTab={initialTab}>`
  (تَأكَّد أن الـshell يَدعم `initialTab` prop — إن لا، أَضِف
  controlled `activeTab`).

- [ ] **G-5 — Update App.tsx routes.**
  في `App.tsx`:
  - `case "shipments-management":` لو الـURL هو `/shipments/<id>` →
    redirect لـ`/import-flow/<id>` (server-side useEffect).

**Verifiable G:** فَتح صفقة من ShipmentManagement → يَفتح
ImportDocumentScreen في tab «الصفقات». فَتح من ClearanceManagement
list → ImportDocumentScreen في tab «التخليص». نفس الشيء للنقل المحلي.

---

### H — Delete Old Forms (30 دقيقة)

> **الهدف:** بَعد التَحقّق الكامل من A..G، احذف الـ3 forms القديمة.

- [ ] **H-1 — Delete ShipmentForm.tsx + subcomponents.**
  ```
  rm frontend_v2/components/procurement/shipments/ShipmentForm.tsx
  rm frontend_v2/components/procurement/shipments/form/ShipmentBasicInfo.tsx
  rm frontend_v2/components/procurement/shipments/form/ShipmentShippingDetails.tsx
  rm frontend_v2/components/procurement/shipments/form/ShipmentStatusVisualizer.tsx
  rm frontend_v2/components/procurement/shipments/form/ShipmentDealsTable.tsx
  rm frontend_v2/components/procurement/shipments/form/ShipmentDealSelector.tsx
  ```
  ثم في `ShipmentManagement.tsx` احذف:
  - import ShipmentForm
  - `viewMode === 'form'` branch
  - `currentShipment` state
  الـlist mode فقط يَبقى.

- [ ] **H-2 — Delete clearance form mode.**
  في `CustomsClearanceManagement.tsx`:
  - احذف `selected !== null` branch (الـside form بـ12 حقل).
  - احذف `formData states` للـclearance edit.
  - الـlist + side panel summary (≤ 3 حقول) فقط يَبقى.
  - النقر على row يَفتح import-flow.

- [ ] **H-3 — Delete local form mode.**
  نفس الشيء لـ`LocalShippingPage.tsx`:
  - احذف الـmodal `EditLocalShipmentModal` و
    `CreateLocalShipmentModal`.
  - الـlist فقط يَبقى.
  - زر «إضافة» يَفتح `/import-flow/new?tab=local`.

- [ ] **H-4 — Remove orphan CSS.**
  `aseel-commercial-band` في `index.css` — احذفه (لم يَعد مُستخدَماً
  بعد task6 P-G-4).

- [ ] **H-5 — Run density-audit.**
  `node frontend_v2/scripts/density-audit.cjs` — وَثِّق العَدّاد
  الجديد (يَجب يَنخفض ~50+ بَعد حَذف الـforms).

**Verifiable H:** `grep -r "ShipmentForm" frontend_v2/` = 0. `npx tsc
--noEmit` لا يَرتفع. الـapp تَعمل: قائمة الشحنات → النقر → editor كامل
في import-flow.

---

### I — AseelSidePanel Primitive (1h)

> **الهدف:** primitive حقيقي بدل CSS hack الذي عَمله الموديل السابق
> على AseelIndexPicker.

- [ ] **I-1 — `frontend_v2/components/aseel/AseelSidePanel.tsx` جديد.**
  ```tsx
  interface AseelSidePanelProps {
    open: boolean;
    onClose: () => void;
    title: string;
    width?: number;  // default 380
    children: React.ReactNode;
  }
  ```
  - يَستخدم portal لـ`document.body`.
  - يَنزلق من اليمين (RTL) بـtransform transition.
  - mask خفيف (opacity .2) لا يَحجُب التَّفاعل تماماً.
  - ESC + click outside يُغلق.
  - aria-busy على الـbody خَلفه.

- [ ] **I-2 — Convert SupplierViewModal to side panel.**
  استبدِل modal بـAseelSidePanel.

- [ ] **I-3 — Convert ShipmentDealSelector** (إن لم يُحذَف في H-1).
  - لو حُذف في H-1: skip.
  - وإلا: convert.

- [ ] **I-4 — Documentation in `docs/ui_density_rules.md`.**
  أَضِف قسم «متى modal ومتى SidePanel»:
  - **Modal:** decision points (confirm, picker بـbig list, error).
  - **SidePanel:** browse/view بدون قَطع التَّفاعل (view supplier,
    deal details, info panes).

**Verifiable I:** AseelSidePanel يُستخدم في 2 موقع على الأقل،
SupplierViewModal محوَّل، الـpicker الأصلي (AseelIndexPicker) يَبقى
modal لأنه decision point.

---

## Verification Matrix

| Phase | Verifiable Goals |
|------|------------------|
| A | shipment header editable · save يَعمل · new shipment يَعمل |
| B | clearance header + lines editable · create-new-clearance يَعمل |
| C | deals link/unlink/allocate يَعمل · sum=100% |
| D | local shipments CRUD يَعمل · ترحيل يَعمل |
| E | clearance payments add يَعمل · totals تَتحدَّث |
| F | convert-to-invoice يَنشئ PurchaseInvoice مَعبَّأة |
| G | routing من Shipments/Clearance/Local لـimport-flow بـtab صحيح |
| H | 3 old forms محذوفة · tsc لا يَرتفع · density-audit يَنخفض |
| I | AseelSidePanel primitive · SupplierView مُحوَّل · docs محدَّثة |

---

## Execution Rules (صارمة)

1. **اقرأ هذا الملف كاملاً + task6.md + ImportDocumentScreen.tsx الحالي
   قبل أي سَطر.**
2. كل sub-phase = commit مستقل بـرسالة `task6.1 <X>-<Y>: <desc>`.
3. اعمل على branch `claude/task6.1`. لا في main.
4. **بَعد كل sub-phase توقَّف وانتظر review.** لا تَقفز.
5. **لا تَخترع endpoints.** إن وَجدت ناقص → `[QUESTION]` في commit body.
6. **لا تَكسر edit button.** قبل G-1 (redirect)، تَأكَّد A..F تَعمل
   100% — وإلا تَكرار البُغ السابق.
7. `tsc --noEmit` بَعد كل sub-phase. العَدّاد لا يَرتفع فوق 41.
8. `manage.py check` = 0 — رغم أن هذه التاسك frontend-only، لكن لو
   لَمست شيء backend تَأكَّد لا drift.
9. **لا dependencies جديدة.** لا lodash، لا framer-motion، لا
   react-hook-form. كل ما تَحتاجه موجود.
10. **density rules دائماً:** كل tab يَدخل في viewport 1080p بدون
    scroll للـcontainer. tabs scroll داخلي فقط.
11. **بَعد H (حذف الـforms القديمة) شغِّل live test كامل:**
    - فَتح شحنة قائمة → تَعديل header → تخزين
    - إنشاء شحنة جديدة → تَعديل → تخزين
    - فَتح tab تخليص → إضافة 3 بنود → تخزين
    - فَتح tab نقل محلي → إضافة سَجَل → ترحيل
    - فَتح tab دفعات → إضافة دفعة شحن
    - زر «تكوين فاتورة» → التَأكُّد أن الفاتورة تَفتح
    لو أيّ واحد فَشل → rollback H وعَلِّق `[BLOCKING]`.

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| editing parity ناقصة وحذف الـforms يَكسر | لا تَحذف الـforms قبل اختبار A..F live |
| state management معقَّد (4 forms في شاشة) | استَخدم separate state per tab، lift up فقط للـtotals |
| race conditions بَين saves متوازية | كل save لـtab مستقل، lock UI أثناء save |
| Workflow transitions تَفشل عبر الـAPI | استَخدم `patchShippingWorkflow` المخصَّص (P-B-6 موجود) |
| فاتورة convert تَفشل لشحنات قديمة | اختبر على شحنات task6 المُحدَّثة (transaction_time + vat_statement موجودة) |

---

## Aseel Reference Cross-Check

| الموضوع | المرجع الأصيل | التَحقّق في import-flow |
|---------|--------------|-------------------------|
| إرسالية header | الإرساليات.txt:1-100 | tab صفقات + header band 22 حقل |
| التخليص | الإرساليات.txt:140-220 | tab «التخليص» editable |
| النقل المحلي | اللوجستيات.txt:5-80 | tab «النقل المحلي» editable |
| الدفعات | المحاسبة.txt:100-150 | tab «الدفعات» يَعمل |
| الفاتورة من إرسالية | الفواتير.txt:300-360 | زر «تكوين فاتورة» |
| الـworkflow timeline | الإرساليات.txt:103-130 | CompactTimeline يَبقى موجود ≤ 32px |

---

## Status

> **Status:** `[ ]` A..I pending owner approval · 2026-05-24
>
> **Total:** 9 sub-phases · ~28 task · 0 migration · 3 forms محذوفة
> في النهاية · 1 primitive جديد (AseelSidePanel).
>
> **Estimated execution:** 8-12 ساعة موديل أرخص + 2 ساعة مراجعة.
>
> **القاعدة:** بَعد التاسك، رحلة الاستيراد كاملة (Shipment → Clearance →
> Local → Invoice) تَتمّ من شاشة واحدة فقط بدون فَتح أي شاشة قديمة.
> الـforms الـ3 القديمة محذوفة. AseelSidePanel primitive جاهز للاستخدام.
