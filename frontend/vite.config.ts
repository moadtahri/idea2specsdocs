import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // WSL + Windows mount: native file watching doesn't fire, poll instead
    watch: { usePolling: true, interval: 500 },
    proxy: {
      // ws: the voice relay (/api/voice/listen) is a WebSocket (spec 09).
      '/api': { target: 'http://localhost:8000', ws: true },
    },
  },
});
