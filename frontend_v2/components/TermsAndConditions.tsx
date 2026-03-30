import React from 'react';

interface TermsAndConditionsProps {
  isOpen: boolean;
  onClose: () => void;
  onAccept: () => void;
}

export const TermsAndConditions: React.FC<TermsAndConditionsProps> = ({ 
  isOpen, 
  onClose, 
  onAccept 
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white text-center">
            الشروط والأحكام
          </h2>
        </div>

        <div className="p-6 space-y-6 text-gray-700 dark:text-gray-300">
          <div className="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded-lg border border-yellow-200 dark:border-yellow-800">
            <p className="text-yellow-800 dark:text-yellow-200 font-bold text-center">
              ⚠️ يرجى قراءة الشروط والأحكام بعناية قبل الموافقة
            </p>
          </div>

          <section>
            <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-3">1. القبول والشروط</h3>
            <p className="mb-4">
              بمجرد إنشاء حسابك في منصتنا، فإنك توافق على الالتزام بهذه الشروط والأحكام بشكل كامل. 
              نحن نحتفظ بالحق في تعديل هذه الشروط في أي وقت، وسيتم إشعارك بأي تغييرات.
            </p>
          </section>

          <section>
            <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-3">2. متطلبات الحساب</h3>
            <ul className="list-disc pr-4 space-y-2">
              <li>يجب أن تكون المعلومات المقدمة صحيحة وكاملة</li>
              <li>يجب أن تكون قد بلغت 18 عاماً على الأقل</li>
              <li>أنت مسؤول عن الحفاظ على سرية حسابك وكلمة المرور</li>
              <li>توافق على تلقي رسائل بريد إلكتروني تتعلق بحسابك</li>
            </ul>
          </section>

          <section>
            <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-3">3. الخصوصية والبيانات</h3>
            <p className="mb-4">
              نحن نحترم خصوصيتك ونلتزم بحماية بياناتك الشخصية. سيتم استخدام معلوماتك فقط للأغراض التالية:
            </p>
            <ul className="list-disc pr-4 space-y-2">
              <li>توفير وتحسين خدماتنا</li>
              <li>التواصل معك بشأن حسابك</li>
              <li>التحقق من الهوية والمؤهلات</li>
              <li>الامتثال للقوانين واللوائح المحلية</li>
            </ul>
          </section>

          <section>
            <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-3">4. المسؤوليات والالتزامات</h3>
            <ul className="list-disc pr-4 space-y-2">
              <li>أنت مسؤول عن جميع الأنشطة التي تتم تحت حسابك</li>
              <li>يجب الإبلاغ عن أي استخدام غير مصرح لحسابك فوراً</li>
              <li>لا يجوز استخدام المنصة لأغراض غير قانونية</li>
              <li>يحق لنا تعليق أو إنهاء الحساب في حالة المخالفة</li>
            </ul>
          </section>

          <section>
            <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-3">5. الملكية الفكرية</h3>
            <p>
              جميع المحتويات والمواد الموجودة على المنصة محمية بحقوق الملكية الفكرية. 
              لا يجوز نسخ أو توزيع أو تعديل أي محتوى بدون إذن كتابي مسبق.
            </p>
          </section>

          <section>
            <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-3">6. حدود المسؤولية</h3>
            <p>
              لن نكون مسؤولين عن أي أضرار غير مباشرة أو تبعية تنشأ عن استخدام المنصة. 
              نحرص على توفير خدمة موثوقة ولكن لا نضمن أن الخدمة ستكون خالية من الأخطاء.
            </p>
          </section>

          <section>
            <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-3">7. الموافقة على المعالجة</h3>
            <p className="mb-4">
              بالموافقة على هذه الشروط، فإنك توافق صراحةً على:
            </p>
            <ul className="list-disc pr-4 space-y-2">
              <li>معالجة بياناتك الشخصية بما في ذلك السيرة الذاتية</li>
              <li>التواصل معك عبر البريد الإلكتروني والهاتف</li>
              <li>تخزين معلوماتك في قواعد البيانات الخاصة بنا</li>
              <li>مشاركة المعلومات مع الجهات المعنية عند الضرورة القانونية</li>
            </ul>
          </section>

          <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border border-blue-200 dark:border-blue-800">
            <p className="text-blue-800 dark:text-blue-200 text-center font-semibold">
              📞 للاستفسارات: يرجى الاتصال على +123456789 أو إرسال بريد إلى support@example.com
            </p>
          </div>
        </div>

        <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-bold py-3 px-4 rounded-lg hover:bg-gray-400 dark:hover:bg-gray-600 transition duration-300"
          >
            إغلاق
          </button>
          <button
            onClick={onAccept}
            className="flex-1 bg-green-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-green-700 transition duration-300"
          >
            أوافق على الشروط
          </button>
        </div>
      </div>
    </div>
  );
};