import { defineConfig } from 'vite';

export default defineConfig({
  // Serve the data/ directory alongside public/ for static assets
  publicDir: 'public',
  server: {
    port: 5173,
    open: true,
  },
  build: {
    outDir: 'dist',
  },
});
