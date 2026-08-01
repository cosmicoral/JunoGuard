import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // PORT lets a supervisor pick the port; 5173 stays the default for `npm run dev`.
  server: { port: Number(loadEnv(mode, ".", "PORT").PORT) || 5173 },
}));
