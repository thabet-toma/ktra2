شغّل `npx playwright test e2e/feature-parity-census.spec.ts` لتوليد `parity-baseline.json`، ثم أعد التشغيل مع `PARITY_MODE=compare` للتحقق.
أضف `PARITY_SHOTS=1` لتوليد لقطات 1440×900 داخل `e2e/parity-shots/baseline/`؛ اللقطات محلية وغير متتبعة في Git.
