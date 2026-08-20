import { useEffect, useState } from 'react';
import { subscribeLinkedTabs, type LinkedTab } from '../utils/tabLink';

/**
 * التبويبات المرتبطة الحيّة (الفاتح ومَن فُتح منّا). القائمة لا تتغيّر إلا عند
 * فتح تبويبٍ أو إغلاقه أو تغيّر شاشته — بلا نبضٍ دوري يعيد الرسم بلا سبب.
 */
export function useLinkedTabs(): LinkedTab[] {
  const [tabs, setTabs] = useState<LinkedTab[]>([]);
  useEffect(() => subscribeLinkedTabs(setTabs), []);
  return tabs;
}
