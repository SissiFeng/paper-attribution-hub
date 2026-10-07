import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
export default defineConfig({
  plugins: [react()], base: '/reading/', publicDir: false,
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  build: { outDir: 'dist-reading', rollupOptions: { input: path.resolve(__dirname, 'reading.html') } },
  server: { port: 5174, proxy: { '/api': { target: 'http://127.0.0.1:8000', rewrite: p => p.replace(/^\/api/, '') } } },
});
