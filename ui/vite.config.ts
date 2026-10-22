import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const appVersion = readFileSync(resolve(process.cwd(), '../VERSION'), 'utf8').trim()

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/lucide-react/')) return 'icons'
        },
      },
    },
  },
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
