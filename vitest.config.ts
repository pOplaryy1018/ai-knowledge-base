import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'
export default defineConfig({ resolve: { alias: {
  '@': fileURLToPath(new URL('./packages/consumer/src', import.meta.url)),
  '@akb/shared': fileURLToPath(new URL('./packages/shared/src', import.meta.url)),
} } })
