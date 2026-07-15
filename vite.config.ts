import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// When Tauri builds for a physical mobile device it serves the frontend from
// the Mac's LAN address and exports it as TAURI_DEV_HOST, so Vite must listen
// on that host (not just localhost) for the phone to reach the dev server.
const host = process.env.TAURI_DEV_HOST

// base './' keeps built assets relative so the same bundle works from
// a web server, a Tauri webview, and Capacitor's file:// container.
export default defineConfig({
  plugins: [react()],
  base: './',
  clearScreen: false,
  server: {
    // host=false → localhost for normal web dev; the LAN IP for mobile dev.
    host: host || false,
    port: 5173,
    strictPort: true,
    hmr: host ? { protocol: 'ws', host, port: 1421 } : undefined,
    watch: { ignored: ['**/src-tauri/**'] },
  },
  build: { outDir: 'dist', target: 'es2020' },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
} as Parameters<typeof defineConfig>[0])
