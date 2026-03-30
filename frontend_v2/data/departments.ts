export interface Department {
  id: string;
  name: string;
  nameEn: string;
  managerTitle: string;
  managerName: string;
  email: string;
  whatsapp: string;
  iconType: 'shipping' | 'finance' | 'support' | 'it' | 'marketing' | 'logistics';
}

export const departments: Department[] = [
  {
    id: 'purchasing',
    name: 'قسم المشتريات والشحن',
    nameEn: 'Purchasing & Shipping Department',
    managerTitle: 'المدير',
    managerName: 'ثابت طعمة',
    email: 'thapet64@gmail.com',
    whatsapp: '970592587483',
    iconType: 'shipping',
  },
  {
    id: 'finance',
    name: 'قسم المالية والتخليص الجمركي',
    nameEn: 'Finance & Customs Clearance Department',
    managerTitle: 'المديرة',
    managerName: 'هيا',
    email: 'engineer.haya93@gmail.com',
    whatsapp: '0599905051',
    iconType: 'finance',
  },
  {
    id: 'support',
    name: 'قسم خدمة العملاء وما بعد البيع',
    nameEn: 'Customer Service & After-Sales Department',
    managerTitle: 'المسؤولة',
    managerName: 'دموع',
    email: 'support@ktra.com',
    whatsapp: '966501234567',
    iconType: 'support',
  },
  {
    id: 'it',
    name: 'قسم الحاسوب والتطوير',
    nameEn: 'IT & Development Department',
    managerTitle: 'المدير',
    managerName: 'يزن عديلي',
    email: 'edaliyazan6@gmail.com',
    whatsapp: '970595498035',
    iconType: 'it',
  },
  {
    id: 'marketing',
    name: 'قسم التسويق والمبيعات',
    nameEn: 'Marketing & Sales Department',
    managerTitle: 'المدير',
    managerName: 'علي',
    email: 'aliamro325@gmail.com',
    whatsapp: '970599627109',
    iconType: 'marketing',
  },
  {
    id: 'logistics',
    name: 'قسم المخازن واللوجستيات',
    nameEn: 'Warehousing & Logistics Department',
    managerTitle: 'المدير',
    managerName: 'أمير',
    email: 'logistics@ktra.com',
    whatsapp: '966501234567',
    iconType: 'logistics',
  },
];