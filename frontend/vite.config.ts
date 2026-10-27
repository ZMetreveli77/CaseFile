import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development (`npm run dev`), Vite serves the UI on :5173 and forwards API calls to uvicorn on :8000.
// In production FastAPI serves the built files itself, so no proxy is needed there.
const BACKEND_URL = 'http://127.0.0.1:8000'
const API_PATHS = ['/health', '/documents', '/sources', '/ask', '/formats']

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(API_PATHS.map((path) => [path, BACKEND_URL])),
  },
})
