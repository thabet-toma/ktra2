# وصف قاعدة بيانات نظام Ktra — مرجع الـ AI Agent

## السياق التجاري
شركة **Ktra** تعمل في **الاستيراد اللوجستي** (Import & Logistics):
- تشتري بضاعة من موردين دوليين (صين بشكل رئيسي)
- تُدير الصفقات والشحنات والتخليص الجمركي
- تُسجّل الدفعات وتربطها بقيود محاسبية
- النظام يدعم شجرة حسابات كاملة (Chart of Accounts) بمحاسبة قيد مزدوج

---

## 1. الجداول الأساسية (Core)

### `tenants` — المستأجرون (الشركات)
| العمود | النوع | الوصف |
|--------|-------|-------|
| TenantID | INT PK | معرف الشركة (القيمة = 1 في النظام الحالي) |
| CompanyName | VARCHAR | اسم الشركة |
| SubscriptionPlan | ENUM(Basic,Pro,Enterprise) | خطة الاشتراك |
| Status | ENUM(Active,Suspended,Trial) | حالة الحساب |

### `currencies` — العملات
| العمود | الوصف |
|--------|-------|
| CurrencyID | PK |
| Code | مثل USD, ILS, CNY |
| Symbol | $ ₪ ¥ |
| IsBaseCurrency | هل هي العملة الأساسية؟ |

### `auth_user` — المستخدمون
| العمود | الوصف |
|--------|-------|
| id | PK |
| username | اسم المستخدم |
| first_name, last_name | الاسم |
| email | البريد |
| is_active | مفعّل؟ |

---

## 2. الشركاء (Partners)

### `partners` — الموردون والعملاء
| العمود | الوصف |
|--------|-------|
| PartnerID | PK |
| TenantID | FK → tenants |
| Name | الاسم التجاري |
| LegalName | الاسم القانوني |
| Type | Supplier / Customer / FreightForwarder / CustomsBroker / LocalTransporter |
| LinkedAccountID | FK → chartofaccounts (حساب الذمم المرتبط) |
| Country, City | الموقع |
| Phone, Email | التواصل |
| CreditLimit | حد الائتمان |
| OpeningBalance | الرصيد الافتتاحي |

> **نوع المورد (Type):**
> - `Supplier` → مورد بضاعة (مصنع)
> - `FreightForwarder` → وكيل شحن
> - `CustomsBroker` → مخلّص جمركي
> - `LocalTransporter` → ناقل محلي

### `partner_bank_accounts` — حسابات بنوك الشركاء
| العمود | الوصف |
|--------|-------|
| PartnerBankAccountID | PK |
| PartnerID | FK → partners |
| BankName, AccountNumber, IBAN, SwiftCode | بيانات البنك |
| BeneficiaryName | اسم المستفيد |

---

## 3. المحاسبة (Accounting)

### `chartofaccounts` — شجرة الحسابات
| العمود | الوصف |
|--------|-------|
| AccountID | PK |
| TenantID | FK → tenants |
| Code | رقم الحساب (مثل 1110, 2100) |
| Name | اسم الحساب (عربي/إنجليزي) |
| ParentID | FK → نفسه (الحساب الأب) |
| Type | Asset / Liability / Equity / Revenue / Expense |
| IsActive | مفعّل؟ |

> **نظام الترقيم الشائع:**
> 1xxx = أصول | 2xxx = التزامات | 3xxx = حقوق ملكية | 4xxx = إيرادات | 5xxx = مصاريف

### `journal_headers` — رؤوس قيود اليومية
| العمود | الوصف |
|--------|-------|
| JournalID | PK |
| TenantID | FK |
| TransactionDate | تاريخ القيد |
| Description | وصف القيد |
| ReferenceType | نوع المرجع: LOGISTICS_PAYMENT / PURCHASE_RECEIPT / LOGISTICS_CLEARANCE_PAYMENT / LOGISTICS_EXPENSE / JOURNAL_REVERSAL |
| ReferenceID | معرف المرجع المرتبط |
| IsPosted | مرحّل؟ (True=مرحّل، False=مسودة) |

### `journal_lines` — أسطر القيود
| العمود | الوصف |
|--------|-------|
| JLineID | PK |
| JournalID | FK → journal_headers |
| AccountID | FK → chartofaccounts |
| Debit | مدين |
| Credit | دائن |
| PartnerID | FK → partners (اختياري) |
| CostCenterID | FK → cost_centers (اختياري) |
| LineDescription | وصف السطر |

> **قاعدة أساسية:** مجموع Debit = مجموع Credit في كل قيد مرحّل.

### `cash_box_ledger_accounts` — ربط الصناديق بالحسابات
| العمود | الوصف |
|--------|-------|
| CashBoxLedgerID | PK |
| ExternalID | معرف الصندوق في Firestore |
| Name | اسم الصندوق |
| AccountID | FK → chartofaccounts |
| CurrencyCode | USD / ILS |

### `cost_centers` — مراكز التكلفة
| العمود | الوصف |
|--------|-------|
| CostCenterID | PK |
| Name, Code | اسم ورمز المركز |

### `fiscal_periods` — الفترات المالية
| العمود | الوصف |
|--------|-------|
| PeriodID | PK |
| PeriodName | مثل "FY 2025" |
| StartDate, EndDate | بداية ونهاية الفترة |
| Status | Open / Closed |

### `accounting_audit_logs` — سجل التدقيق
تسجيل كل عملية إنشاء/تعديل/ترحيل على القيود.

---

## 4. اللوجستيات (Logistics) — الجوهر

### `logistics_deals` — صفقات الشراء
| العمود | الوصف |
|--------|-------|
| DealID | PK |
| TenantID | FK |
| RefNumber | رقم مرجعي (مثل INV-001) |
| PartnerID | FK → partners (المورد) |
| OrderDate | تاريخ الطلب |
| TotalAmount | إجمالي الصفقة (بعد الخصم والضريبة) |
| CurrencyID | FK → currencies |
| Status | Open / Shipped / Cleared / Closed / Cancelled |
| PaymentStatus | Unpaid / Partially Paid / Fully Paid |
| OrderStatus | Open / Manufacturing / ReadyToShip / Shipping / Clearance / Delivered / Closed |
| shipping_workflow_status | مرحلة الشحن: sw_mfg_start / sw_wait_agent_ship / sw_wait_intl_ship / sw_wait_arrival / sw_wait_clearance / sw_released |
| pi_number | رقم الـ PI |
| factory_name | اسم المصنع |
| subtotal | المجموع قبل الخصم |
| discount_amount | مبلغ الخصم |
| tax_rate, tax_amount | الضريبة |
| shipping_cost_estimate | تقدير تكلفة الشحن للصفقة |
| total_cbm | الحجم الإجمالي (m³) |
| total_weight_kg | الوزن الإجمالي (kg) |
| IsPosted | هل رُحّل قيد الشراء؟ |
| JournalID | FK → journal_headers |
| CreatedAt | تاريخ الإنشاء |

### `logistics_deal_items` — بنود الصفقة
| العمود | الوصف |
|--------|-------|
| DealItemID | PK |
| DealID | FK → logistics_deals |
| ProductID | FK → products |
| Quantity | الكمية |
| UnitPrice | سعر الوحدة |

### `logistics_payments` — دفعات الصفقات والشحنات
| العمود | الوصف |
|--------|-------|
| PaymentID | PK |
| DealID | FK → logistics_deals (null للدفعات المرتبطة بشحنة فقط) |
| LinkedShipmentID | FK → logistics_shipments (null للدفعات المرتبطة بصفقة فقط) |
| PaymentNumber | رقم الدفعة (1, 2, 3, …) |
| Title | وصف الدفعة (مثل: "دفعة أولى") |
| Amount | المبلغ (USD) |
| Status | Pending / ClaimUploaded / Paid / Confirmed |
| TransferDate | تاريخ التحويل |
| ConfirmationDate | تاريخ التأكيد |
| IsPosted | هل رُحّل قيد؟ |
| JournalID | FK → journal_headers |
| cash_box_external_id | معرف الصندوق المستخدم |
| bank_swift_image | صورة الـ SWIFT |
| confirmed_by_supplier | هل أكّد المورد الاستلام؟ |

> **ملاحظة:** إذا DealID مملوء → دفعة للمورد. إذا LinkedShipmentID مملوء → دفعة لوكيل الشحن.

### `logistics_shipments` — الشحنات
| العمود | الوصف |
|--------|-------|
| ShipmentID | PK |
| TenantID | FK |
| ShipmentNumber | رقم الشحنة |
| ShippingAgentID | FK → partners (وكيل الشحن) |
| Status | Pending / In-Transit / Arrived / Clearing / Cleared |
| shipment_route_status | agent_warehouse / china_customs_clearance / on_board / at_sea / arrived_port / israel_customs_clearance / released / delivered_local |
| total_shipping_cost_usd | إجمالي تكلفة الشحن (USD) |
| BillOfLading | رقم بوليصة الشحن |
| ContainerNumber | رقم الحاوية |
| DepartureDate | تاريخ المغادرة |
| ArrivalDate | تاريخ الوصول |
| shipment_name | اسم وصفي للشحنة |
| shipping_type | sea / air |

### `logistics_shipment_deals` — ربط الصفقات بالشحنات
| العمود | الوصف |
|--------|-------|
| LinkID | PK |
| ShipmentID | FK → logistics_shipments |
| DealID | FK → logistics_deals |

> صفقة واحدة قد تكون في شحنة واحدة فقط. شحنة واحدة قد تحتوي عدة صفقات.

### `logistics_clearance` — التخليص الجمركي
| العمود | الوصف |
|--------|-------|
| ClearanceID | PK |
| TenantID | FK |
| ShipmentID | FK → logistics_shipments (OneToOne — شحنة واحدة = تخليص واحد) |
| CustomsBrokerID | FK → partners (المخلّص الجمركي) |
| DeclarationNumber | رقم البيان الجمركي |
| ClearanceDate | تاريخ التخليص |
| Status | Processing / Cleared / Hold |
| cost_lines | JSON: [{"label": "ضريبة القيمة المضافة", "amount": 500}, ...] |
| Notes | ملاحظات |

### `logistics_clearance_payments` — دفعات التخليص
| العمود | الوصف |
|--------|-------|
| ClearancePaymentID | PK |
| ClearanceID | FK → logistics_clearance |
| CustomsBrokerID | FK → partners |
| Amount | المبلغ (USD) |
| PaymentDate | تاريخ الدفع |
| CashBoxExternalID | معرف الصندوق |
| IsPosted | هل رُحّل القيد؟ |
| JournalID | FK → journal_headers |

### `logistics_expenses` — مصاريف لوجستية
| العمود | الوصف |
|--------|-------|
| ExpenseID | PK |
| RelatedType | Deal / Shipment / Clearance |
| RelatedID | معرف المرتبط |
| ExpenseAccountID | FK → chartofaccounts |
| PayableAccountID | FK → chartofaccounts |
| Amount | المبلغ |
| Description | الوصف |
| IsPosted | مرحّل؟ |

---

## 5. المنتجات والمخزون

### `products`
| العمود | الوصف |
|--------|-------|
| ProductID | PK |
| SKU | رمز المنتج |
| Name_AR, Name_EN | الاسم عربي/إنجليزي |
| CategoryID | FK → product_categories |
| HS_Code | رمز النظام المنسق للجمارك |
| Weight_KG, Volume_CBM | الوزن والحجم |

### `product_categories`
هيكل شجري للفئات (parent/child).

### `stock_ledger` — حركة المخزون
سجل دخول وخروج كل منتج من كل مستودع.

### `warehouses` / `warehouse_locations`
المستودعات والمواقع داخلها.

---

## 6. المبيعات

### `salesinvoices` — فواتير البيع
| العمود | الوصف |
|--------|-------|
| InvoiceDate | تاريخ الفاتورة |
| PartnerID | FK → partners (العميل) |
| TotalAmount | الإجمالي |
| Status | Draft / Posted / Cancelled |

### `salesinvoice_lines` — بنود الفاتورة
### `customer_receipts` — إيصالات استلام العميل

---

## 7. المشتريات

### `purchaseorders` — أوامر الشراء
### `po_lines` — بنود أمر الشراء
### `vendor_payments` — مدفوعات الموردين

---

## 8. نقاط البيع (POS)
`pos_sales`, `pos_sale_lines`, `pos_payments`, `pos_sessions`, `pos_terminals`

---

## 9. الموارد البشرية
`employees`, `payroll_runs`, `payroll_slips`

---

## 10. CRM
`crm_leads`, `crm_opportunities`, `crm_contacts`, `crm_pipeline_stages`, `crm_activities`

---

## العلاقات الأهم (للاستعلامات المشتركة)

```
partners ──────────────────┐
   │                       │
logistics_deals ──── logistics_shipment_deals ──── logistics_shipments
   │                                                       │
logistics_payments                             logistics_clearance
   │                                                       │
journal_headers ◄──────────────────────────── logistics_clearance_payments
   │
journal_lines ──── chartofaccounts
```

### استعلامات شائعة:
```sql
-- كل صفقات مورد معين مع حالة الدفع
SELECT d.DealID, d.RefNumber, d.TotalAmount, d.PaymentStatus, p.Name as supplier
FROM logistics_deals d
JOIN partners p ON d.PartnerID = p.PartnerID
WHERE p.Name LIKE '%اسم المورد%' AND d.TenantID = 1;

-- مجموع مدفوعات كل صفقة مقابل قيمتها
SELECT d.RefNumber, d.TotalAmount,
       COALESCE(SUM(py.Amount),0) as TotalPaid,
       d.TotalAmount - COALESCE(SUM(py.Amount),0) as Remaining
FROM logistics_deals d
LEFT JOIN logistics_payments py ON py.DealID = d.DealID AND py.Status IN ('Paid','Confirmed')
WHERE d.TenantID = 1
GROUP BY d.DealID, d.RefNumber, d.TotalAmount;

-- شحنة وصفقاتها والمورد
SELECT sh.ShipmentNumber, sh.Status, d.RefNumber, p.Name as supplier
FROM logistics_shipments sh
JOIN logistics_shipment_deals sd ON sd.ShipmentID = sh.ShipmentID
JOIN logistics_deals d ON d.DealID = sd.DealID
JOIN partners p ON d.PartnerID = p.PartnerID
WHERE sh.TenantID = 1;

-- القيود غير المرحّلة (مسودات)
SELECT JournalID, TransactionDate, Description, ReferenceType
FROM journal_headers
WHERE IsPosted = 0 AND TenantID = 1
ORDER BY TransactionDate DESC;

-- ميزان المراجعة للحسابات
SELECT a.Code, a.Name, SUM(jl.Debit) as TotalDebit, SUM(jl.Credit) as TotalCredit
FROM journal_lines jl
JOIN chartofaccounts a ON jl.AccountID = a.AccountID
JOIN journal_headers jh ON jl.JournalID = jh.JournalID
WHERE jh.IsPosted = 1 AND jh.TenantID = 1
GROUP BY a.AccountID, a.Code, a.Name;
```
