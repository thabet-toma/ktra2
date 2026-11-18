# النشر على الإنتاج

إجراء المنسّق في خطوة «الاستلام» (بطلب المالك 2026-10-22). **المرجع مهارة الخادم
`deploy-local-to-modern`** (`/root/.claude/skills/deploy-local-to-modern/SKILL.md`)، وتُقرأ قبل كل
نشرٍ إن تغيّرت. السكربت `deploy2.sh` في الـscratchpad، ويُعاد إنشاؤه من هذه الخطوات إن ضاع.

- **الإنتاج:** `ktra-pro.tech` = `root@187.124.164.58`، المجلد `/root/ktra`، الفرع `modern`.
- **الاتصال:** `ssh -i ~/.ssh/hostenger2/id_ed25519 root@187.124.164.58`.

## الخطوات

1. **محلياً:** `git push origin newktra`.
2. **CI أخضر على آخر commit** (`gh run list --branch newktra`). عند `failure` لا نشر حتى يُصلَح أو
   يُثبَت أنه الفشل البيئي المعروف وحده.
3. **على الخادم:** `git fetch` ثم `git merge origin/newktra`. عند تعارض: `git merge --abort` والتوقّف.
4. **الثابت:** `git diff origin/newktra` فارغ (إعدادات المضيف رُحّلت إلى `newktra`). أيّ ملفٍ يظهر ⇒
   توقّف.
5. `pip install` و`npm install`.
6. **البوّابات الخفيفة وحدها:** `manage.py check` و`makemigrations --check` والهجرات المعلّقة، و`npm run
   build`. **لا `pytest` ولا `tsc` على الخادم**: نواةٌ واحدة بلا swap وهو الإنتاج الحي، وCI يشغّلها.
7. **مراجعة كل هجرةٍ جديدة:** `RemoveField` أو `DeleteModel` أو `RunSQL` ⇒ توقّف واسأل المالك.
8. **إن وُجدت هجرة: نسخةٌ احتياطية أوّلاً**، `mysqldump` ببيانات `.env` الخادم إلى `/root/backups/`.
9. `migrate`.
10. `collectstatic` ونشر الـstatic.
11. `rsync` لـ`dist/` **مستثنياً كل ما في جذر الويب وليس من `dist/`**: مجلد مشاركة PDF يعيش هناك،
    و`--delete` يمحوه.
12. `systemctl restart ktra.service`.
13. **التحقّق:**
    - `is-active`، و`NRestarts` = 0.
    - ثلاثُ `curl` تردّ 200: `127.0.0.1:8000/api/health/` و`https://ktra-pro.tech/api/health/` و
      `https://ktra-pro.tech/`.
    - سجلّ `logs/gunicorn-error.log`.
    - نقاط الوكيل `/api/agent/{products,customers,suppliers,invoices}/`.

## حواجز

- **لا `push` من الخادم:** المهارة تمنعه بلا إذنٍ صريح.
- **أيّ فشلٍ قبل `migrate`:** `git reset --hard` إلى ما قبل الدمج. الخدمة لم يُعَد تشغيلها بعد، فالإنتاج
  لم يتغيّر.
