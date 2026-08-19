import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

// Flat config (ESLint 9/10). The TypeScript parser is required so .ts/.tsx
// files don't trip the default parser on `interface`/type-annotation syntax.
// We intentionally keep the rule set minimal (react-hooks only) to match the
// project's existing lint scope without flooding the legacy tree.
export default [
  {
    // `smart-product-search-platform/` مجلد دخيل غير متتبَّع في git ولا يدخله
    // البناء — لا يُفرض عليه قانون المشروع ولا يُصلَح ضمن هذه المهمة.
    ignores: ['dist/**', 'node_modules/**', 'dev-dist/**', 'playwright-report/**', 'smart-product-search-platform/**'],
  },
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      // The two canonical Rules of Hooks. `rules-of-hooks` is a real
      // correctness gate (error); `exhaustive-deps` is advisory (warn) so it
      // doesn't fail CI. The stricter rules added in react-hooks v7 are left
      // off intentionally — enabling them would flag ~120 pre-existing issues
      // across the legacy tree that are out of scope for this change.
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // SAVE-4: نوافذ المتصفح ممنوعة بقانون المشروع (useToast / useConfirm
      // بدلاً عنها). كان القانون مكتوباً بلا حارس، فخُرق في 36 ملفاً — بينها
      // شاشات مالية تأخذ رقم قيد يومية وعدد شيكات من `window.prompt`.
      // القاعدة تجعله مفروضاً آلياً بدل الاعتماد على المراجعة.
      'no-restricted-globals': [
        'error',
        { name: 'alert', message: 'استعمل useToast بدل alert.' },
        { name: 'confirm', message: 'استعمل useConfirm بدل confirm.' },
        { name: 'prompt', message: 'استعمل PromptDialog بدل prompt.' },
      ],
      // `no-restricted-globals` تلتقط الاستدعاء المجرّد وحده. وتهجئة
      // `window.prompt(...)` هي بالضبط ما أخفى أربعة ملفات مالية عن الجرد
      // اليدوي في هذه المهمة — فالثغرة ليست نظرية. بدونها يبقى الحارس
      // يُطمئن دون أن يحرس.
      'no-restricted-properties': [
        'error',
        { object: 'window', property: 'alert', message: 'استعمل useToast بدل window.alert.' },
        { object: 'window', property: 'confirm', message: 'استعمل useConfirm بدل window.confirm.' },
        { object: 'window', property: 'prompt', message: 'استعمل PromptDialog بدل window.prompt.' },
        { object: 'globalThis', property: 'alert', message: 'استعمل useToast بدل globalThis.alert.' },
        { object: 'globalThis', property: 'confirm', message: 'استعمل useConfirm بدل globalThis.confirm.' },
        { object: 'globalThis', property: 'prompt', message: 'استعمل PromptDialog بدل globalThis.prompt.' },
      ],
    },
  },
];
