import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  APPLICANT_STATUS_OPTIONS,
  CV_ACCEPT_ATTRIBUTE,
  EMPLOYMENT_TYPE_OPTIONS,
  MAX_CV_BYTES,
  applicantStatusBadgeClass,
  cvFileProblem,
  filterPlatformApplicants,
  firstApiErrorMessage,
  passwordProblem,
} from './platformHiring.ts';

test('cvFileProblem يمرّر ملفاً سليماً ولا يشكو من غياب الملف', () => {
  assert.equal(cvFileProblem({ name: 'CV.PDF', size: 2048 }), null);
  assert.equal(cvFileProblem(null), null);
  assert.equal(cvFileProblem(undefined), null);
});

test('cvFileProblem يرفض الامتداد قبل الحجم — ملفٌّ مرفوضُ النوع لا يعني حجمُه شيئاً', () => {
  assert.match(cvFileProblem({ name: 'resume.exe', size: MAX_CV_BYTES + 1 }) ?? '', /نوع الملف/);
  assert.match(cvFileProblem({ name: 'noextension', size: 10 }) ?? '', /نوع الملف/);
  // نقطةٌ في أوّل الاسم ليست امتداداً
  assert.match(cvFileProblem({ name: '.pdf', size: 10 }) ?? '', /نوع الملف/);
});

test('cvFileProblem يرفض الفارغ وما فوق السقف ويقبل السقف نفسَه', () => {
  assert.equal(cvFileProblem({ name: 'a.pdf', size: 0 }), 'الملف فارغ.');
  assert.match(cvFileProblem({ name: 'a.pdf', size: MAX_CV_BYTES + 1 }) ?? '', /يتجاوز الحد/);
  assert.equal(cvFileProblem({ name: 'a.pdf', size: MAX_CV_BYTES }), null);
});

test('CV_ACCEPT_ATTRIBUTE مبنيٌّ من قائمة الامتدادات نفسِها', () => {
  assert.equal(CV_ACCEPT_ATTRIBUTE, '.pdf,.doc,.docx,.jpg,.jpeg,.png,.webp');
});

test('passwordProblem: القِصَرُ ثمّ عدمُ التطابق ثمّ القبول', () => {
  assert.match(passwordProblem('1234567', '1234567') ?? '', /(?:ألّا|لا)\s*تقل/);
  assert.equal(passwordProblem('12345678', '12345679'), 'كلمتا المرور غير متطابقتين.');
  assert.equal(passwordProblem('12345678', '12345678'), null);
});

test('firstApiErrorMessage يستخرج رسالة DRF بأشكالها الثلاثة', () => {
  assert.equal(firstApiErrorMessage({ detail: 'انتهى التقديم.' }, 'x'), 'انتهى التقديم.');
  assert.equal(firstApiErrorMessage({ email: ['أدخل بريداً صحيحاً.'] }, 'x'), 'أدخل بريداً صحيحاً.');
  assert.equal(firstApiErrorMessage({ cv: 'الملف فارغ.' }, 'x'), 'الملف فارغ.');
  assert.equal(firstApiErrorMessage(['أوّل', 'ثانٍ'], 'x'), 'أوّل');
  assert.equal(firstApiErrorMessage({ outer: { inner: ['عميقة'] } }, 'x'), 'عميقة');
});

test('firstApiErrorMessage يسقط على البديل حين لا رسالة', () => {
  assert.equal(firstApiErrorMessage(null, 'تعذّر الإرسال.'), 'تعذّر الإرسال.');
  assert.equal(firstApiErrorMessage({}, 'تعذّر الإرسال.'), 'تعذّر الإرسال.');
  assert.equal(firstApiErrorMessage({ detail: '   ' }, 'تعذّر الإرسال.'), 'تعذّر الإرسال.');
  assert.equal(firstApiErrorMessage('', 'تعذّر الإرسال.'), 'تعذّر الإرسال.');
});

test('applicantStatusBadgeClass: لونٌ لكلّ حالةٍ معروفة، ومحايدٌ لما لا يعرفه', () => {
  assert.match(applicantStatusBadgeClass('hired'), /emerald/);
  assert.match(applicantStatusBadgeClass('rejected'), /rose/);
  assert.match(applicantStatusBadgeClass('future_status'), /slate/);
  assert.match(applicantStatusBadgeClass(null), /slate/);
});

test('APPLICANT_STATUS_OPTIONS وEMPLOYMENT_TYPE_OPTIONS معرّفة وتحتوي على الحالات المتوقعة', () => {
  assert.equal(APPLICANT_STATUS_OPTIONS.length, 6);
  assert.equal(APPLICANT_STATUS_OPTIONS[0].value, 'new');
  assert.equal(APPLICANT_STATUS_OPTIONS[5].value, 'rejected');

  assert.equal(EMPLOYMENT_TYPE_OPTIONS.length, 4);
  assert.equal(EMPLOYMENT_TYPE_OPTIONS[0].value, 'full_time');
  assert.equal(EMPLOYMENT_TYPE_OPTIONS[3].value, 'temporary');
});

test('filterPlatformApplicants: تصفية المتقدمين بالاسم أو الهاتف أو البريد أو رمز المرجع', () => {
  const applicants = [
    { name: 'أحمد علي', phone: '0599123456', email: 'ahmad@example.com', reference_code: 'REF-AHMAD-1' },
    { name: 'خالد عمر', phone: '0566987654', email: 'khaled@test.local', reference_code: 'REF-KHALED-2' },
    { name: 'سارة يوسف', phone: '0599000111', email: 'sara@platform.local', reference_code: 'REF-SARA-3' },
  ];

  // بحث فارغ يُعيد الكل كما هو
  assert.equal(filterPlatformApplicants(applicants, '').length, 3);
  assert.equal(filterPlatformApplicants(applicants, '   ').length, 3);

  // بالاسم
  const byName = filterPlatformApplicants(applicants, 'أحمد');
  assert.equal(byName.length, 1);
  assert.equal(byName[0].name, 'أحمد علي');

  // بالهاتف
  const byPhone = filterPlatformApplicants(applicants, '0566');
  assert.equal(byPhone.length, 1);
  assert.equal(byPhone[0].name, 'خالد عمر');

  // بالبريد
  const byEmail = filterPlatformApplicants(applicants, 'platform.local');
  assert.equal(byEmail.length, 1);
  assert.equal(byEmail[0].name, 'سارة يوسف');

  // برمز المرجع
  const byRef = filterPlatformApplicants(applicants, 'KHALED-2');
  assert.equal(byRef.length, 1);
  assert.equal(byRef[0].name, 'خالد عمر');

  // استعلام غير موجود يُعيد مصفوفة فارغة
  assert.equal(filterPlatformApplicants(applicants, 'غير_موجود').length, 0);
});

