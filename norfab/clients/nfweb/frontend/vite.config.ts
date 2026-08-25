import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const sourceMaps = process.env.NFWEB_SOURCEMAPS === "true";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../static",
    emptyOutDir: true,
    sourcemap: sourceMaps ? "hidden" : false,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:9005",
    },
  },
});
