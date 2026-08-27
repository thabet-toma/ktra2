import React from "react";
import { KitDocumentShell } from "../kit/KitDocumentShell";

/**
 * إطار شاشات البيانات الخام (الصفقات · الشحنات · المنتجات · الأطراف).
 *
 * T-WIN M7: كان بطاقةً مرتجلة (`p-4` + `h1` + صندوق مدوّر) خارج الغلاف
 * الموحّد — فالشاشات الأربع كانت الوحيدة بلا شريط عنوان ولا شريط أوامر ولا
 * شريط حالة، ولا يصلها تلميع الجلد. صار الإطار `KitDocumentShell`، فورثت
 * الأربع كلها بتعديل ملفٍ واحد ولم يتغيّر سطرٌ في أيٍّ منها.
 *
 * `actions` تُمرَّر كما هي إلى الشريط العلوي (وليست `KitToolbarAction[]`)
 * لأنها في هذه الشاشات خليطُ أزرارٍ وحقولِ بحثٍ وقوائم — تمريرها كما هي يُبقي
 * نصوصها ومعرّفاتها حرفاً بحرف كما كانت.
 */
export function SqlDataPageShell(props: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <KitDocumentShell
      title={props.title}
      company={props.subtitle}
      header={props.actions ? <div className="flex flex-wrap items-center gap-2">{props.actions}</div> : undefined}
    >
      {props.children}
    </KitDocumentShell>
  );
}
