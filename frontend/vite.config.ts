import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev: `npm run dev` runs in mock mode (see .env.development); `npm run dev:api` talks to the
// FastAPI backend on :8000 through the /api proxy. Production build never includes the mocks.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1100,
  },
})
