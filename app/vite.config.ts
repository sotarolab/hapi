import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Deployed by .github/workflows/pages.yml to GitHub Pages under /hapi/. The data comes from the
// repository's data branch over raw.githubusercontent.com (see src/api.ts); in development
// VITE_DATA_BASE=/sitedata proxies to `python -m http.server 8070` run inside ../data/site
// (SITEDATA=http://localhost:<port> overrides the target when 8070 is busy).
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE ?? '/hapi/',
  server: { proxy: { '/sitedata': { target: process.env.SITEDATA ?? 'http://localhost:8070', changeOrigin: true, rewrite: (p) => p.replace(/^\/sitedata/, '') } } },
  build: { outDir: 'dist', emptyOutDir: true },
})
