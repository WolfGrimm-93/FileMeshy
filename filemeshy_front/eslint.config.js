import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
        },
      ],
    },
  },
  {
    // Las secciones de plantillas PDF deben soportar un modo dual PDF/HTML
    // (ver src/shared/utils/pdf/primitives.tsx). Por eso View/Text/Image/
    // StyleSheet no deben importarse directo de @react-pdf/renderer aqui:
    // deben venir siempre de '../primitives', que decide en tiempo de
    // render si usa los componentes reales de react-pdf o su equivalente
    // HTML/CSS. Otras importaciones de @react-pdf/renderer (Svg, Path,
    // Font, Document, Page, etc.) siguen permitidas.
    files: ['src/shared/utils/pdf/sections/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@react-pdf/renderer',
              importNames: ['View', 'Text', 'Image', 'StyleSheet'],
              message:
                'Importa View/Text/Image/StyleSheet desde "../primitives" (no directo de @react-pdf/renderer). ' +
                'Ese archivo puentea entre el render PDF real y el preview HTML/CSS del editor; ' +
                'importar estos nombres directo de react-pdf rompe el modo web del preview.',
            },
          ],
        },
      ],
    },
  },
])
