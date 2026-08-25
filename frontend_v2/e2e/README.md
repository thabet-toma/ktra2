`npx playwright test e2e/feature-parity-census.spec.ts` **يقارن** بخطّ الأساس `parity-baseline.json` — هذا هو الافتراض.
لإعادة تسجيل خطّ الأساس (نيّةٌ تُعلَن، وتُراجَع في الـdiff قبل الحفظ): `PARITY_MODE=record npx playwright test e2e/feature-parity-census.spec.ts`.
لا تُعِد التسجيل إلا بعد أن تعرف **لماذا** اختلف الحصاد: زرٌّ أُضيف عمداً يُبلَّغ عنه تحذيراً (`[parity] … new …`) ويمرّ أخضر، أمّا النقصان فيُخفق — وهو ما بُني الحارس له.
أضف `PARITY_SHOTS=1` لتوليد لقطات 1440×900 داخل `e2e/parity-shots/baseline/`؛ اللقطات محلية وغير متتبعة في Git.
