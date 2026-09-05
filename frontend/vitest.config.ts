import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./test/setup.ts'],
    include: ['__tests__/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    clearMocks: true,
    mockReset: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary', 'html'],
      reportsDirectory: './coverage',
      include: [
        'app/**/*.{ts,tsx}',
        'components/**/*.{ts,tsx}',
        'hooks/**/*.{ts,tsx}',
        'services/**/*.ts',
        'store/**/*.ts',
        'utils/**/*.ts',
      ],
      exclude: [
        '**/*.d.ts',
        'app/layout.tsx',
        'components/ui/index.ts',
      ],
      thresholds: {
        statements: 80,
        branches: 75,
        functions: 75,
        lines: 80,
        'services/apiClient.ts': {
          statements: 90,
          branches: 90,
          functions: 90,
          lines: 90,
        },
        'services/authService.ts': {
          statements: 85,
          branches: 80,
          functions: 85,
          lines: 85,
        },
        'services/projectService.ts': {
          statements: 90,
          branches: 75,
          functions: 90,
          lines: 90,
        },
        'services/storageService.ts': {
          statements: 90,
          branches: 80,
          functions: 70,
          lines: 90,
        },
        'app/editor/**/page.tsx': {
          statements: 50,
          branches: 50,
          functions: 20,
          lines: 50,
        },
        'utils/editorWorkflow.ts': {
          statements: 90,
          branches: 85,
          functions: 70,
          lines: 90,
        },
      },
    },
  },
});
