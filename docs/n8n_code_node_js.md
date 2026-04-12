# كود JavaScript لعقدة Code في n8n (بدل Python)

في عقدة Code:
- Language: **JavaScript**
- Mode: **Run Once for All Items**

الصق هذا الكود:

```javascript
const payStatusAr = {
  'Unpaid': 'غير مدفوعة',
  'Partially Paid': 'مدفوعة جزئياً',
  'Fully Paid': 'مدفوعة بالكامل'
};

const orderStatusAr = {
  'Open': 'مفتوحة',
  'Manufacturing': 'قيد التصنيع',
  'ReadyToShip': 'جاهزة للشحن',
  'Shipping': 'قيد الشحن',
  'Clearance': 'قيد التخليص',
  'Delivered': 'تم التسليم',
  'Closed': 'مغلقة'
};

const workflowAr = {
  'sw_mfg_start': 'بدأ التصنيع',
  'sw_wait_agent_ship': 'انتظار الشحن للوكيل',
  'sw_wait_intl_ship': 'عند الوكيل انتظار الشحن الدولي',
  'sw_wait_arrival': 'في الطريق انتظار الوصول',
  'sw_wait_clearance': 'وصلت انتظار التخليص الجمركي',
  'sw_released': 'تم التخليص وجاهزة'
};

const output = [];

for (const item of $input.all()) {
  const r = item.json;

  const total   = parseFloat(r.TotalAmount  || 0);
  const paid    = parseFloat(r.paid_amount  || 0);
  const remaining = Math.max(0, total - paid).toFixed(2);

  const supplierLegal = r.supplier_legal ? ` (${r.supplier_legal})` : '';
  const workflow = workflowAr[r.shipping_workflow_status] || r.shipping_workflow_status || 'لم يبدأ';

  const text = [
    `صفقة: ${r.RefNumber || ''}`,
    `المورد: ${r.supplier_name || ''}${supplierLegal}`,
    `الدولة: ${r.supplier_country || 'غير محدد'}`,
    `المصنع: ${r.factory_name || 'غير محدد'}`,
    `رقم PI: ${r.pi_number || 'غير محدد'}`,
    `الوصف: ${r.deal_description || ''}`,
    `المبلغ الإجمالي: $${total.toLocaleString()}`,
    `المدفوع: $${paid.toLocaleString()} | المتبقي: $${remaining}`,
    `حالة الدفع: ${payStatusAr[r.PaymentStatus] || r.PaymentStatus || ''}`,
    `عدد الدفعات: ${r.payments_count || 0}`,
    `حالة الطلب: ${orderStatusAr[r.OrderStatus] || r.OrderStatus || ''}`,
    `مرحلة الشحن: ${workflow}`,
    `المنتجات: ${r.products_text || 'لا توجد بنود'}`,
    `بيانات بحث المنتجات: ${r.products_search || ''}`,
    `الشحنة: ${r.shipment_number || 'لم تُشحن'}`,
    `حالة الشحنة: ${r.shipment_status || 'غير محدد'}`,
    `تاريخ الإنشاء: ${r.created_date || ''}`,
  ].join('\n');

  // نسخة مطبّعة لتحسين استرجاع الموديلات والقدرات (IHDC4200 / 3000W=4200VA)
  const normalized = text
    .toLowerCase()
    // توحيد الحروف العربية (الهمزات + التاء المربوطة)
    .replace(/[أإآ]/g, 'ا')
    .replace(/ة/g, 'ه')
    // IHDC4200 -> IHDC 4200 | 3000W -> 3000 W
    .replace(/([a-zA-Z]+)(\d+)/g, '$1 $2')
    .replace(/(\d+)([a-zA-Z]+)/g, '$1 $2')
    .replace(/[=/_\-]+/g, ' ')
    .replace(/[^a-z0-9\u0600-\u06FF\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  // مرادفات وصفية شائعة تساعد الاسترجاع
  const normalizedBoosted =
    (normalized.includes('yellow inverter') ||
      normalized.includes('انفيرتر اصفر') ||
      normalized.includes('انفرتر اصفر'))
      ? `${normalized} انفيرتر اصفر انفرتر اصفر انفيرتر أصفر yellow inverter`
      : normalized;

  output.push({
    json: {
      pageContent: `${text.trim()}\n--- بيانات بحث إضافية ---\n${normalizedBoosted}`,
      metadata: {
        deal_id: String(r.DealID || ''),
        ref_number: String(r.RefNumber || ''),
        supplier: String(r.supplier_name || ''),
        payment_status: String(r.PaymentStatus || ''),
        order_status: String(r.OrderStatus || ''),
        source: 'logistics_deal_combined'
      }
    }
  });
}

return output;
```
