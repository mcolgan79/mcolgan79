import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' keeps built assets relative so the same bundle works from
// a web server, a Tauri webview, and Capacitor's file:// container.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', target: 'es2020' },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
} as Parameters<typeof defineConfig>[0])
