import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend runs on a mandatory fixed port (Google OAuth javascript_origins pins
// http://localhost:4000). strictPort makes a port clash fail loudly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 4000,
    strictPort: true,
  },
  preview: {
    port: 4000,
    strictPort: true,
  },
});
