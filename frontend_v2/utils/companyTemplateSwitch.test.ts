import { test } from 'node:test';
import assert from 'node:assert/strict';
import { diffTemplateSwitch } from './companyTemplateSwitch.ts';
import { TEMPLATE_HIDDEN_VIEWS } from './viewPermissions.ts';

test('general → accounting_firm: كل شاشات المكتب المخفيّة تختفي، ولا شيء يظهر', () => {
  const diff = diffTemplateSwitch('general', 'accounting_firm');
  assert.deepEqual(diff.appearing, []);
  assert.deepEqual(
    diff.disappearing,
    [...TEMPLATE_HIDDEN_VIEWS.accounting_firm].sort(),
  );
});

test('accounting_firm → general: نفس الشاشات تظهر، ولا شيء يختفي (عكس الاتجاه)', () => {
  const diff = diffTemplateSwitch('accounting_firm', 'general');
  assert.deepEqual(diff.disappearing, []);
  assert.deepEqual(
    diff.appearing,
    [...TEMPLATE_HIDDEN_VIEWS.accounting_firm].sort(),
  );
});

test('نفس القالب من والى ⇒ لا شيء يظهر ولا شيء يختفي', () => {
  const diff = diffTemplateSwitch('accounting_firm', 'accounting_firm');
  assert.deepEqual(diff.appearing, []);
  assert.deepEqual(diff.disappearing, []);
});

test('قالبٌ غائب (undefined/null) يُطبَّع general — بلا إخفاء', () => {
  assert.deepEqual(diffTemplateSwitch(undefined, 'accounting_firm').appearing, []);
  assert.deepEqual(
    diffTemplateSwitch(undefined, 'accounting_firm').disappearing,
    [...TEMPLATE_HIDDEN_VIEWS.accounting_firm].sort(),
  );
  assert.deepEqual(diffTemplateSwitch('accounting_firm', null), {
    appearing: [...TEMPLATE_HIDDEN_VIEWS.accounting_firm].sort(),
    disappearing: [],
  });
});

test('قالبٌ غير مسجَّل يُعامَل كـ general', () => {
  const diff = diffTemplateSwitch('not-a-real-template', 'accounting_firm');
  assert.deepEqual(diff.appearing, []);
  assert.deepEqual(diff.disappearing, [...TEMPLATE_HIDDEN_VIEWS.accounting_firm].sort());
});
