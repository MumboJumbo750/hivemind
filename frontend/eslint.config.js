import js from '@eslint/js'
import ts from 'typescript-eslint'
import vue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'

export default [
  // Base JS rules
  js.configs.recommended,

  // TypeScript rules
  ...ts.configs.recommended,

  // Vue rules
  ...vue.configs['flat/recommended'],

  // Vue + TypeScript parser setup
  {
    files: ['src/**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: ts.parser,
        extraFileExtensions: ['.vue'],
      },
    },
  },

  // TypeScript files
  {
    files: ['src/**/*.ts'],
    languageOptions: {
      parser: ts.parser,
    },
  },

  // Project-wide rules
  {
    rules: {
      // Vue
      'vue/multi-word-component-names': 'off', // HivemindCard etc. ist OK
      'vue/require-default-prop': 'off',        // withDefaults() ist ausreichend
      'vue/no-v-html': 'warn',

      // TypeScript
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],

      // Allgemein
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },

  // Architecture: UI-Primitives dürfen keine Domain-Logik importieren
  {
    files: ['src/components/ui/**/*.vue', 'src/components/ui/**/*.ts'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [
          { group: ['**/stores/**', '../../stores/**'], message: 'UI-Primitives dürfen keine Stores importieren.' },
          { group: ['**/api/**', '../../api/**'],       message: 'UI-Primitives dürfen keine API-Calls machen.' },
        ],
      }],
    },
  },

  // Ignorierte Pfade
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      'src/api/client/**',   // generierter Code
    ],
  },
]
