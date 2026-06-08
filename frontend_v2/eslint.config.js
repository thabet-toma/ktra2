import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

// Flat config (ESLint 9/10). The TypeScript parser is required so .ts/.tsx
// files don't trip the default parser on `interface`/type-annotation syntax.
// We intentionally keep the rule set minimal (react-hooks only) to match the
// project's existing lint scope without flooding the legacy tree.
export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'dev-dist/**', 'playwright-report/**'],
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
    },
  },
];
